import os
import time
import heapq
import struct
from heap_file import read_page, write_page, count_pages

#funciones auxiliares

def init_empty_page_file(filepath: str):
    """Crea un archivo binario vacío para que 'r+b' de write_page no falle."""
    with open(filepath, 'wb') as f:
        pass

def get_max_records_per_page(page_size: int, record_format: str) -> int:
    """Calcula cuántos registros caben considerando tus 4 bytes de header."""
    header_size = 4
    record_size = struct.calcsize(record_format)
    return (page_size - header_size) // record_size


#generacion de runs

def generate_runs(heap_path: str, page_size: int, buffer_size: int, sort_key_idx: int, record_format: str) -> list[str]:
    B = buffer_size // page_size
    total_pages = count_pages(heap_path, page_size)
    run_paths = []
    
    #carpeta temporal para los run.bin
    temp_dir = "temp_runs"
    os.makedirs(temp_dir, exist_ok=True)

    current_page = 0
    run_id = 0
    pages_read_total = 0
    pages_written_total = 0
    
    while current_page < total_pages:
        buffer_records = []
        pages_read_in_run = 0
        
        #leer hasta B paginas
        while pages_read_in_run < B and current_page < total_pages:
            records = read_page(heap_path, current_page, page_size, record_format)
            buffer_records.extend(records)
            current_page += 1
            pages_read_in_run += 1
            pages_read_total += 1
            
        if not buffer_records:
            break
            
        #ordenar buffer completo en RAM por la columna indicada
        buffer_records.sort(key=lambda x: x[sort_key_idx])
        
        #archivo temporal para el run
        run_path = os.path.join(temp_dir, f"run_{run_id}.bin")
        init_empty_page_file(run_path)
        
        max_records = get_max_records_per_page(page_size, record_format)
        run_page_id = 0
        
        for i in range(0, len(buffer_records), max_records):
            page_slice = buffer_records[i : i + max_records]
            _write_sequential_page(run_path, page_slice, record_format, page_size)
            pages_written_total += 1
            run_page_id += 1
            
        run_paths.append(run_path)
        run_id += 1
        
    return run_paths, pages_read_total, pages_written_total

def _write_sequential_page(filepath, records, record_format, page_size):
    record_size = struct.calcsize(record_format)
    with open(filepath, 'ab') as file:
        page = bytearray(page_size)
        struct.pack_into('i', page, 0, len(records))
        offset = 4
        for record in records:
            struct.pack_into(record_format, page, offset, *record)
            offset += record_size
        file.write(page)


#multiway merge

def multiway_merge(run_paths: list[str], output_path: str, page_size: int, buffer_size: int, sort_key_idx: int, record_format: str):
    init_empty_page_file(output_path)
    max_records = get_max_records_per_page(page_size, record_format)
    
    pages_read_total = 0
    pages_written_total = 0

    def run_reader(path):
        nonlocal pages_read_total
        num_pages = count_pages(path, page_size)
        for p_id in range(num_pages):
            records = read_page(path, p_id, page_size, record_format)
            pages_read_total += 1
            for r in records:
                yield r

    min_heap = []
    readers = [run_reader(path) for path in run_paths]
    
    #llenar el min-heap inicial con el primer registro de cada run
    for run_idx, reader in enumerate(readers):
        try:
            first_record = next(reader)
            heapq.heappush(min_heap, (first_record[sort_key_idx], run_idx, first_record))
        except StopIteration:
            continue

    output_buffer = []

    while min_heap:
        val, run_idx, record = heapq.heappop(min_heap)
        output_buffer.append(record)
        
        #si output buffer (1 página) se llena, escribir a disco
        if len(output_buffer) >= max_records:
            _write_sequential_page(output_path, output_buffer, record_format, page_size)
            pages_written_total += 1
            output_buffer = []
        
        #extraer siguiente registro del run que acaba de ser popeado
        try:
            next_record = next(readers[run_idx])
            heapq.heappush(min_heap, (next_record[sort_key_idx], run_idx, next_record))
        except StopIteration:
            pass

    if output_buffer:
        _write_sequential_page(output_path, output_buffer, record_format, page_size)
        pages_written_total += 1

    return pages_read_total, pages_written_total




def external_sort(heap_path: str, output_path: str, page_size: int, buffer_size: int, sort_key_idx: int, record_format: str) -> dict:
    start_total = time.time()
    
    #runs
    start_f1 = time.time()
    runs, f1_read, f1_write = generate_runs(heap_path, page_size, buffer_size, sort_key_idx, record_format)
    end_f1 = time.time()
    
    #multiway merge
    start_f2 = time.time()
    f2_read, f2_write = multiway_merge(runs, output_path, page_size, buffer_size, sort_key_idx, record_format)
    end_f2 = time.time()
    

    for r in runs:
        if os.path.exists(r):
            os.remove(r)

    try:
        os.rmdir("temp_runs")
    except OSError:
        pass
            
    end_total = time.time()
    
    return {
        'runs_generated': len(runs),
        'pages_read': f1_read + f2_read,
        'pages_written': f1_write + f2_write,
        'time_phase1_sec': end_f1 - start_f1,
        'time_phase2_sec': end_f2 - start_f2,
        'time_total_sec': end_total - start_total
    }

#ejemplo
if __name__ == "__main__":
    # Ajusta los parámetros según tus pruebas
    heap_origen = "data/employee.bin"
    heap_ordenado = "heap_sorted.bin"
    formato = "q20s5s15s15s15s15s15s"
    
    PAGE_SIZE_LAB = 4096
    BUFFER_SIZE_LAB = 65536  # 64 KB
    indice_columna_orden = 7 # 7 es el índice para hire_date en la nueva tupla
    
    metricas = external_sort(
        heap_path=heap_origen,
        output_path=heap_ordenado,
        page_size=PAGE_SIZE_LAB,
        buffer_size=BUFFER_SIZE_LAB, 
        sort_key_idx=indice_columna_orden, 
        record_format=formato
    )
    
    print("\nMétricas del External Sort:")
    for k, v in metricas.items():
        print(f"{k}: {v}")
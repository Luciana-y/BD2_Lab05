import os
import time
import struct
import csv

def fix_str(s, size):
    """Ajusta un string a un tamaño fijo en bytes rellenando con nulos."""
    return s.encode('utf-8')[:size].ljust(size, b'\x00')

def export_to_heap(csv_path: str, heap_path: str, record_format: str, page_size: int):
    """Exporta el CSV de department_employee al binario paginado."""
    record_size = struct.calcsize(record_format)
    header_size = 4
    records_per_page = (page_size - header_size) // record_size

    # Asegurar que el directorio de salida exista
    os.makedirs(os.path.dirname(heap_path), exist_ok=True)

    with open(csv_path, 'r', encoding='utf-8') as csv_file, open(heap_path, 'wb') as heap_file:

        reader = csv.reader(csv_file, delimiter=',') 
        next(reader) 

        page_records = []
        for row in reader:
            if len(row) < 4: continue # Evitar filas vacias
            
            record = (
                int(row[0]),          # employee_id: bigint -> q
                fix_str(row[1], 4),   # department_id: char(4) -> 4s
                fix_str(row[2], 10),  # from_date: date -> 10s
                fix_str(row[3], 10)   # to_date: date -> 10s
            )
            page_records.append(record)

            if len(page_records) >= records_per_page:
                _write_page_raw(heap_file, page_records, record_format, page_size)
                page_records = []

        if page_records:
            _write_page_raw(heap_file, page_records, record_format, page_size)

def _write_page_raw(file, records, record_format, page_size):
    record_size = struct.calcsize(record_format)
    header_size = 4
    page = bytearray(page_size)
    struct.pack_into('i', page, 0, len(records))
    offset = header_size
    for record in records:
        struct.pack_into(record_format, page, offset, *record)
        offset += record_size
    file.write(page)

def read_page(heap_path: str, page_id: int, page_size: int, record_format: str) -> list[tuple]:
    if not os.path.exists(heap_path): return []
    with open(heap_path, 'rb') as f:
        f.seek(page_id * page_size)
        page = f.read(page_size)
        if not page or len(page) < 4: return []
        num_records = struct.unpack_from("i", page, 0)[0]
        offset = 4
        record_size = struct.calcsize(record_format)
        records = []
        for _ in range(num_records):
            rec = struct.unpack_from(record_format, page, offset)
            records.append(rec)
            offset += record_size
        return records

def count_pages(heap_path: str, page_size: int) -> int:
    if not os.path.exists(heap_path): return 0
    size = os.path.getsize(heap_path)
    return (size + page_size - 1) // page_size


# Hashing aux funcs

def init_empty_page_file(filepath: str):
    with open(filepath, 'wb') as f:
        pass

def get_max_records_per_page(page_size: int, record_format: str) -> int:
    return (page_size - 4) // struct.calcsize(record_format)

def _write_sequential_page(filepath: str, records: list[tuple], record_format: str, page_size: int):
    record_size = struct.calcsize(record_format)
    with open(filepath, 'ab') as file:
        page = bytearray(page_size)
        struct.pack_into('i', page, 0, len(records))
        offset = 4
        for record in records:
            struct.pack_into(record_format, page, offset, *record)
            offset += record_size
        file.write(page)

# external hashing

def partition_data(heap_path: str, page_size: int, buffer_size: int, group_key_idx: int, record_format: str) -> tuple[list[str], int, int]:
    B = buffer_size // page_size
    k = B - 1
    if k <= 0: k = 1
    
    total_pages = count_pages(heap_path, page_size)
    temp_dir = "temp_partitions"
    os.makedirs(temp_dir, exist_ok=True)
    
    partition_paths = []
    for i in range(k):
        path = os.path.join(temp_dir, f"part_{i}.bin")
        init_empty_page_file(path)
        partition_paths.append(path)
    
    output_buffers = [[] for _ in range(k)]
    max_records = get_max_records_per_page(page_size, record_format)
    
    pages_read_total = 0
    pages_written_total = 0
    
    for p_id in range(total_pages):
        records = read_page(heap_path, p_id, page_size, record_format)
        pages_read_total += 1
        
        for rec in records:
            key_value = rec[group_key_idx]
            part_idx = hash(key_value) % k
            
            output_buffers[part_idx].append(rec)
            
            if len(output_buffers[part_idx]) >= max_records:
                _write_sequential_page(partition_paths[part_idx], output_buffers[part_idx], record_format, page_size)
                pages_written_total += 1
                output_buffers[part_idx] = []
                
    for i in range(k):
        if output_buffers[i]:
            _write_sequential_page(partition_paths[i], output_buffers[i], record_format, page_size)
            pages_written_total += 1
            
    return partition_paths, pages_read_total, pages_written_total

def aggregate_partitions(partition_paths: list[str], page_size: int, group_key_idx: int, record_format: str) -> tuple[dict, int]:
    final_counts = {}
    pages_read_total = 0
    
    for path in partition_paths:
        num_pages = count_pages(path, page_size)
        for p_id in range(num_pages):
            records = read_page(path, p_id, page_size, record_format)
            pages_read_total += 1
            for rec in records:
                val = rec[group_key_idx]
                if isinstance(val, bytes):
                    val = val.decode('utf-8').strip('\x00')
                final_counts[val] = final_counts.get(val, 0) + 1
                
    return final_counts, pages_read_total

def external_hash_group_by(heap_path: str, page_size: int, buffer_size: int, group_key_idx: int, record_format: str) -> dict:
    start_total = time.time()
    
    start_f1 = time.time()
    partition_paths, f1_read, f1_write = partition_data(heap_path, page_size, buffer_size, group_key_idx, record_format)
    end_f1 = time.time()
    
    start_f2 = time.time()
    counts, f2_read = aggregate_partitions(partition_paths, page_size, group_key_idx, record_format)
    end_f2 = time.time()
    
    # Limpieza de archivos
    for p in partition_paths:
        if os.path.exists(p): os.remove(p)
    try:
        os.rmdir("temp_partitions")
    except OSError:
        pass
        
    return {
        'result': counts,
        'partitions_created': len(partition_paths),
        'pages_read': f1_read + f2_read,
        'pages_written': f1_write,
        'time_phase1_sec': end_f1 - start_f1,
        'time_phase2_sec': end_f2 - start_f2,
        'time_total_sec': time.time() - start_total
    }

# resultados

if __name__ == "__main__":
    
    csv_origen = "data/department_employee.csv"
    heap_origen = "data/department_employee.bin"
    
    
    FORMATO = "q4s10s10s"
    INDICE_FROM_DATE = 2  # from_date esta en pos 2
    PAGE_SIZE_LAB = 4096  # 4 KB
    
    if not os.path.exists(heap_origen):
        print(f"Exportando CSV a Heap File ({heap_origen})...")
        if os.path.exists(csv_origen):
            export_to_heap(csv_origen, heap_origen, FORMATO, PAGE_SIZE_LAB)
            print(f"Exportación completada. Total de páginas: {count_pages(heap_origen, PAGE_SIZE_LAB)}")
        else:
            print(f"ERROR: No se encontró el archivo CSV en la ruta: {csv_origen}")
            exit(1)


    tamanos_buffer = [64 * 1024, 128 * 1024, 256 * 1024]

    print("analisis del External Hashing")

    for buffer_size in tamanos_buffer:
        print(f"\nBUFFER_SIZE = {buffer_size // 1024} KB")
        metricas = external_hash_group_by(
            heap_path=heap_origen,
            page_size=PAGE_SIZE_LAB,
            buffer_size=buffer_size,
            group_key_idx=INDICE_FROM_DATE,
            record_format=FORMATO
        )

        print(f"Particiones creadas (k): {metricas['partitions_created']}")
        print(f"I/O Total: {metricas['pages_read'] + metricas['pages_written']}")
        print(f"Tiempo Fase 1: {metricas['time_phase1_sec']:.5f} s")
        print(f"Tiempo Fase 2: {metricas['time_phase2_sec']:.5f} s")
        print(f"Tiempo Total:  {metricas['time_total_sec']:.5f} s")

        if buffer_size == 64 * 1024:
            print(f"\nMuestra de Resultados (total {len(metricas['result'])} grupos distintos):")
            for k, v in list(metricas['result'].items())[:5]:
                print(f"  Fecha: {k} -> Empleados: {v}")
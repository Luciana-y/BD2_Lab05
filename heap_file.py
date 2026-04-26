import csv
import struct
import os


def fix_str(s, size):
    return s.encode('utf-8')[:size].ljust(size, b'\x00')


# Exporta un CSV a un heap file binario paginado.
def export_to_heap(csv_path: str, heap_path: str, record_format: str, page_size: int):
    record_size = struct.calcsize(record_format)
    header_size = 4

    records_per_page = (page_size - header_size) // record_size

    print("record_size:", record_size)
    print("records_per_page:", records_per_page)

    with open(csv_path, 'r') as csv_file, open(heap_path, 'wb') as heap_file:
        reader = csv.reader(csv_file,delimiter=';')

        next(reader)  #saltar header

        page_records = []

        for row in reader:
            record = (
                int(row[0]),          # q
                fix_str(row[1], 20),  # 20s
                fix_str(row[2], 5),   # 5s
                fix_str(row[3], 15),  # 15s
                fix_str(row[4], 15),  # 15s
                fix_str(row[5], 15),  # 15s
                fix_str(row[6], 15),  # 15s
                fix_str(row[7], 15)   # 15s
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

    max_records = (page_size - header_size) // record_size

    if len(records) > max_records:
        raise ValueError(f"Too many records: {len(records)} > {max_records}")

    page = bytearray(page_size)

    struct.pack_into('i', page, 0, len(records))

    offset = header_size
    for record in records:
        struct.pack_into(record_format, page, offset, *record)
        offset += record_size

    file.write(page)

# Lee una página del heap file y retorna sus registros.
def read_page(heap_path: str, page_id: int, page_size: int, record_format: str) -> list[tuple]:
    records = []

    with open(heap_path, 'rb') as f:
        f.seek(page_id * page_size)
        page = f.read(page_size)

        if not page:
            return []

        num_records = struct.unpack_from("i", page, 0)[0]

        offset = 4
        record_size = struct.calcsize(record_format)

        for _ in range(num_records):
            rec = struct.unpack_from(record_format, page, offset)
            records.append(rec)
            offset += record_size

    return records


# Escribe una lista de registros en la página indicada.
def write_page(heap_path: str, page_id: int, records: list[tuple], record_format: str,
page_size: int):
    with open(heap_path, 'r+b') as file:
        file.seek(page_id * page_size)

        record_size = struct.calcsize(record_format)
        header_size = 4

        page = bytearray(page_size)
        struct.pack_into('i', page, 0, len(records))

        offset = header_size
        for record in records:
            struct.pack_into(record_format, page, offset, *record)
            offset += record_size
        file.write(page)


# Retorna el número total de páginas del heap file.
def count_pages(heap_path: str, page_size: int) -> int:
    sieze = os.path.getsize(heap_path)
    return (sieze + page_size - 1) // page_size

def main():
    csv_path = "data/employee.csv"
    heap_path = "data/employee.bin"

    # q: ID (8 bytes)
    # 20s: Name
    # 5s: Age
    # 15s: Country
    # 15s: Department
    # 15s: Role
    # 15s: Salary
    # 15s: HireDate
    
    record_format = "q20s5s15s15s15s15s15s"
    
    page_size = 4096  # byte

    print("Exportando CSV a Heap File...")
    export_to_heap(csv_path, heap_path, record_format, page_size)

    print("Conteo de páginas...")
    total_pages = count_pages(heap_path, page_size)
    print(f"Total páginas: {total_pages}")

    print("\nLeyendo páginas...\n")

    for page_id in range(total_pages):
        print(f"--- Página {page_id} ---")
        records = read_page(heap_path, page_id, page_size, record_format)

        for rec in records:
            id_val = rec[0]
            name_val = rec[1].decode('utf-8').strip('\x00')
            dept_val = rec[4].decode('utf-8').strip('\x00')
            hire_date = rec[7].decode('utf-8').strip('\x00')

            print(f"id: {id_val}, name: {name_val}, dept: {dept_val}, hired: {hire_date}")
        print()

if __name__ == "__main__":
    main()

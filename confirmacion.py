from heap_file import read_page, count_pages

def verificar_orden(heap_path: str, page_size: int, record_format: str, sort_key_idx: int):
    total_pages = count_pages(heap_path, page_size)
    
    valor_anterior = None
    total_registros = 0
    esta_ordenado = True

    print(f"Iniciando escaneo de {total_pages} páginas...")

    for page_id in range(total_pages):
        records = read_page(heap_path, page_id, page_size, record_format)
        
        for rec in records:
            total_registros += 1
            # Extraemos el valor y lo limpiamos para compararlo bien
            valor_actual = rec[sort_key_idx]
            
            if valor_anterior is not None:
                # Si el anterior es MAYOR que el actual, ¡el ordenamiento falló!
                if valor_anterior > valor_actual:
                    print(f"\n❌ ERROR de ordenamiento en el registro {total_registros} (Página {page_id})")
                    print(f"Anterior: {valor_anterior}")
                    print(f"Actual:   {valor_actual}")
                    esta_ordenado = False
                    return False # Detenemos el escaneo al primer error
            
            valor_anterior = valor_actual

    if esta_ordenado:
        print(f"\n✅ ¡ÉXITO! Se escanearon {total_registros} registros y el archivo está perfectamente ordenado.")
        return True

if __name__ == "__main__":
    heap_ordenado = "C:\\Users\\Rodrigo Zambrano\\OneDrive\\Documentos\\bd2\\lab4\\BD2_Lab05\\heap_sorted.bin"
    formato = "q20s5s15s15s15s15s15s"
    
    PAGE_SIZE_LAB = 4096
    indice_columna_orden = 7 # Tu columna hire_date
    
    verificar_orden(heap_ordenado, PAGE_SIZE_LAB, formato, indice_columna_orden)
import os

def listar_formatos(carpeta):
    formatos = set()  # Usamos un conjunto para evitar duplicados

    for ruta, _, archivos in os.walk(carpeta):
        for archivo in archivos:
            _, extension = os.path.splitext(archivo)
            if extension:  # Evita archivos sin extensión
                formatos.add(extension.lower())

    return sorted(formatos)

# Ejemplo de uso
if __name__ == "__main__":
    ruta_carpeta = input("Introduce la ruta de la carpeta: ").strip()
    
    if os.path.isdir(ruta_carpeta):
        formatos = listar_formatos(ruta_carpeta)
        print("\nFormatos encontrados:")
        for f in formatos:
            print(f)
        print(f"\nTotal de formatos distintos: {len(formatos)}")
    else:
        print("La ruta especificada no es válida.")

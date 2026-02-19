import super_cpp
import time
import matplotlib.pyplot as plt

# --- PARÁMETROS DE LA SIMULACIÓN ---
CLIENTES = 10_000_000  # ¡Diez millones de clientes!
TASA_LLEGADA = 50.0    # Llegan 50 clientes por hora
TASA_SERVICIO = 60.0   # El cajero atiende 60 por hora (es rápido)

print(f"🏭 Iniciando Simulación M/M/1 con {CLIENTES:,} clientes...")
print(f"   Llegadas (lambda): {TASA_LLEGADA}/h | Servicio (mu): {TASA_SERVICIO}/h")
print("-" * 50)

# 1. Instanciar el objeto C++ desde Python
simulador = super_cpp.Simulador(TASA_LLEGADA, TASA_SERVICIO)

# 2. Ejecutar (Medimos el tiempo)
start = time.time()
resultado = simulador.correr(CLIENTES)
end = time.time()

# 3. Mostrar Resultados Numéricos
print(f"✅ Simulación completada en {end - start:.4f} segundos.")
print("-" * 50)
print(f"📊 RESULTADOS:")
print(f"   Tiempo Promedio en Fila:    {resultado.avg_wait:.4f} horas")
print(f"   Tiempo Promedio en Sistema: {resultado.avg_sys:.4f} horas")
print(f"   Utilización del Cajero:     {resultado.utilization * 100:.2f}%")

# Verificación teórica (Fórmula de colas: Wq = lambda / (mu * (mu - lambda)))
# Solo válida si rho < 1
teorico = TASA_LLEGADA / (TASA_SERVICIO * (TASA_SERVICIO - TASA_LLEGADA))
print(f"   [Teórico Esperado:          {teorico:.4f} horas]")

# 4. Visualización (Gráfico)
print("\n📈 Generando histograma de tiempos de espera...")
try:
    plt.figure(figsize=(10, 6))
    plt.hist(resultado.wait_samples, bins=50, color='skyblue', edgecolor='black', alpha=0.7)
    plt.title('Distribución de Tiempos de Espera (Muestra)')
    plt.xlabel('Tiempo de Espera (Horas)')
    plt.ylabel('Frecuencia')
    plt.grid(axis='y', alpha=0.5)
    
    # Guardar gráfico en archivo (porque estamos en Linux/Terminal)
    plt.savefig('resultado_simulacion.png')
    print("✅ Gráfico guardado como 'resultado_simulacion.png'")
except Exception as e:
    print(f"No se pudo graficar: {e}")
import streamlit as st
import random
import pandas as pd
import plotly.express as px
import numpy as np

# Configuración de página
st.set_page_config(page_title="El Mito de la Fila", layout="wide")

st.title("🛒 La Falacia del Supermercado: ¿Por qué la fila te miente?")
st.markdown("""
**El Problema:** Los supermercados asumen que si estás en la posición 10, esperarás lo mismo siempre.
**La Realidad:** La posición en la fila NO sirve para medir tiempo si no sabes cuántos cajeros hay abiertos.
""")

# --- MOTOR DE SIMULACIÓN CORREGIDO ---
def simular_escenario_fijo(n_cajeros, tasa_servicio, n_clientes=1000):
    reloj = 0.0
    # Cajeros: Guarda el momento (reloj) en que cada cajero se libera
    cajeros_liberacion = [0.0] * n_cajeros 
    # Salidas: Guarda el momento en que cada cliente anterior sale del sistema
    tiempos_salida_anteriores = []
    
    resultados = []
    
    # Forzamos tráfico alto para que se armen colas largas
    # (Llegan un 30% más rápido de lo que los cajeros pueden atender)
    tasa_llegada = (n_cajeros * tasa_servicio) * 1.3
    
    for _ in range(n_clientes):
        # 1. Llega un cliente
        intervalo = random.expovariate(tasa_llegada)
        reloj += intervalo
        
        # 2. CÁLCULO DE LA FILA (CORREGIDO)
        # Filtramos: ¿Quiénes siguen dentro del banco cuando yo llego?
        # (Aquellos cuya hora de salida es mayor a mi hora de llegada)
        gente_en_sistema = [t for t in tiempos_salida_anteriores if t > reloj]
        
        # Actualizamos la lista para no acumular memoria infinita
        tiempos_salida_anteriores = gente_en_sistema 
        
        total_personas_delante = len(gente_en_sistema)
        
        # La fila real es: Gente en sistema MENOS los que están siendo atendidos (n_cajeros)
        # Si hay menos gente que cajeros, la fila es 0.
        posicion_en_fila = max(0, total_personas_delante - n_cajeros)
        
        # 3. Asignación de Cajero
        # Buscamos el cajero que se desocupa primero
        cajero_idx = cajeros_liberacion.index(min(cajeros_liberacion))
        momento_liberacion = cajeros_liberacion[cajero_idx]
        
        # El servicio empieza cuando llego O cuando el cajero se libera (lo que pase último)
        inicio_atencion = max(reloj, momento_liberacion)
        
        duracion = random.expovariate(tasa_servicio)
        fin_atencion = inicio_atencion + duracion
        
        # Actualizamos estado del cajero y lista de salidas
        cajeros_liberacion[cajero_idx] = fin_atencion
        tiempos_salida_anteriores.append(fin_atencion)
        
        # 4. Guardar Datos
        espera_min = (inicio_atencion - reloj) * 60
        
        # Solo guardamos si tuvo que hacer fila (para limpiar el gráfico)
        if posicion_en_fila > 0:
            resultados.append({
                "Escenario": f"{n_cajeros} Cajeros",
                "Metros de Fila": posicion_en_fila,
                "Tiempo Espera Real (Min)": espera_min
            })
            
    return pd.DataFrame(resultados)

# --- SIDEBAR ---
with st.sidebar:
    st.header("Configuración")
    VELOCIDAD = st.slider("Velocidad Cajero (Pax/hora)", 10, 60, 20)
    CARTEL_POSICION = st.slider("Posición del Cartel", 5, 40, 15)
    
    run_btn = st.button("🚨 SIMULAR AHORA", type="primary")

# --- LÓGICA DE VISUALIZACIÓN ---
if run_btn:
    with st.spinner("Simulando colas masivas..."):
        # Escenarios: Pocos, Medios y Muchos cajeros
        df1 = simular_escenario_fijo(2, VELOCIDAD)
        df2 = simular_escenario_fijo(6, VELOCIDAD)
        df3 = simular_escenario_fijo(12, VELOCIDAD)
        
        df_total = pd.concat([df1, df2, df3])

    if df_total.empty:
        st.warning("No se generaron suficientes datos de cola. Intenta bajar la velocidad de los cajeros.")
    else:
        # 1. GRÁFICO DE DISPERSIÓN CON TENDENCIA
        st.subheader("Evidencia Visual: Las líneas no coinciden")
        fig = px.scatter(
            df_total, 
            x="Metros de Fila", 
            y="Tiempo Espera Real (Min)", 
            color="Escenario",
            opacity=0.4,
            trendline="ols", # Usamos regresión lineal simple (más robusto que lowess)
            title=f"Si estás en el metro {CARTEL_POSICION} de la fila, ¿cuánto esperas?",
            labels={"Metros de Fila": "Posición en la Fila (Personas delante)", "Tiempo Espera Real (Min)": "Tiempo de Espera (Min)"}
        )
        
        # Línea del cartel
        fig.add_vline(x=CARTEL_POSICION, line_dash="dash", line_color="black", annotation_text="CARTEL")
        fig.add_hline(y=15, line_dash="dot", line_color="red", annotation_text="Límite Paciencia")
        
        st.plotly_chart(fig, use_container_width=True)
        
        # 2. ANÁLISIS NUMÉRICO EN EL PUNTO DEL CARTEL
        st.subheader(f"Análisis en la Posición #{CARTEL_POSICION}")
        
        col1, col2, col3 = st.columns(3)
        
        # Función auxiliar para buscar el valor promedio cercano a la posición
        def get_espera_promedio(df, pos):
            # Filtramos gente que estuvo entre la posición-1 y posición+1
            subset = df[(df["Metros de Fila"] >= pos-1) & (df["Metros de Fila"] <= pos+1)]
            if subset.empty: return 0.0
            return subset["Tiempo Espera Real (Min)"].mean()

        e1 = get_espera_promedio(df1, CARTEL_POSICION)
        e2 = get_espera_promedio(df2, CARTEL_POSICION)
        e3 = get_espera_promedio(df3, CARTEL_POSICION)
        
        col1.metric("Con 2 Cajeros", f"{e1:.1f} min", delta="Lentísimo", delta_color="inverse")
        col2.metric("Con 6 Cajeros", f"{e2:.1f} min", delta="Normal", delta_color="off")
        col3.metric("Con 12 Cajeros", f"{e3:.1f} min", delta="Rápido", delta_color="normal")
        
        st.info("""
        **Moraleja:** El cartel miente.
        La distancia física (posición) no sirve para predecir el tiempo si no consideras la capacidad instalada (Cajeros).
        """)
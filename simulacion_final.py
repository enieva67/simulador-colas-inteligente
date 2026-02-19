import streamlit as st
import heapq
import random
from collections import deque
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# ==========================================
# 1. CLASES Y LÓGICA (BACKEND)
# ==========================================

def curva_demanda_diaria(hora_actual, tasa_base):
    # Patrón de demanda: Mañana baja, pico mediodía, tarde media
    if 0 <= hora_actual < 2: factor = 0.5
    elif 2 <= hora_actual < 4: factor = 1.0
    elif 4 <= hora_actual < 6: factor = 2.0 # HORA PICO FUERTE
    elif 6 <= hora_actual <= 8: factor = 0.7
    else: factor = 0.1
    return tasa_base * factor

class Cliente:
    def __init__(self, id, hora_llegada):
        self.id = id
        self.hora_llegada = hora_llegada
        self.hora_inicio_atencion = None
        self.hora_salida = None
        self.largo_cola_al_llegar = 0

class Servidor:
    def __init__(self, id):
        self.id = id
        self.activo = False
        self.ocupado = False
        # Métricas precisas
        self.tiempo_acumulado_activo = 0.0
        self.tiempo_acumulado_trabajando = 0.0 # Ocupado atendiendo

class SimulacionFinal:
    def __init__(self, tasa_base, tasa_servicio, min_serv, max_serv, umbral_up, umbral_down):
        self.tasa_base = tasa_base
        self.mu = tasa_servicio
        self.min_servers = min_serv
        self.max_servers = max_serv
        self.umbral_up = umbral_up / 60.0
        self.umbral_down = umbral_down / 60.0
        
        self.reloj = 0.0
        self.cola_clientes = deque()
        self.servidores = [Servidor(i) for i in range(max_serv)]
        
        # Inicializar servidores mínimos
        for i in range(min_serv): 
            self.servidores[i].activo = True
            
        self.eventos = []
        self.historial_clientes = []
        self.log_sistema = [] # Log periódico del sistema
        
        # Métricas de Control
        self.cambios_infra = 0

    def _actualizar_cronometros(self, delta_tiempo):
        """
        CORRECCIÓN DE UTILIZACIÓN:
        Avanza el tiempo acumulado de los servidores activos.
        Si está activo (sea ocupado o libre), suma al denominador.
        """
        for s in self.servidores:
            if s.activo:
                s.tiempo_acumulado_activo += delta_tiempo

    def _get_tasa_actual(self):
        return curva_demanda_diaria(self.reloj, self.tasa_base)

    def _registrar_estado(self):
        activos = sum(1 for s in self.servidores if s.activo)
        ocupados = sum(1 for s in self.servidores if s.ocupado)
        
        self.log_sistema.append({
            'Tiempo_Exacto': self.reloj,
            'Cola': len(self.cola_clientes),
            'Servidores_Activos': activos,
            'Servidores_Ocupados': ocupados,
            'Wait_Time_Estimado': self._calcular_ewt() * 60
        })

    def _calcular_ewt(self):
        activos = sum(1 for s in self.servidores if s.activo)
        if activos == 0: return 999.0
        # Fórmula simple: Gente delante / tasa de despacho total
        return len(self.cola_clientes) / (activos * self.mu)

    def _gestionar_escalado(self, ewt_actual):
        activos = sum(1 for s in self.servidores if s.activo)
        
        # Lógica de histéresis
        if ewt_actual > self.umbral_up and activos < self.max_servers:
            # ENCENDER: Buscamos inactivo
            for s in self.servidores:
                if not s.activo:
                    s.activo = True
                    self.cambios_infra += 1
                    return 
        elif ewt_actual < self.umbral_down and activos > self.min_servers:
            # APAGAR: Buscamos activo pero desocupado (desde el último)
            for i in range(self.max_servers - 1, -1, -1):
                s = self.servidores[i]
                if s.activo and not s.ocupado:
                    s.activo = False
                    self.cambios_infra += 1
                    return

    def correr(self):
        self._programar_llegada()
        
        progress_bar = st.progress(0)
        
        while self.eventos:
            tiempo_evento, tipo, data = heapq.heappop(self.eventos)
            
            # Cierre a las 8 horas
            if tipo == "LLEGADA" and tiempo_evento > 8.0: continue
            
            # 1. CRUCIAL: Actualizar cronómetros ANTES de mover el reloj
            delta = tiempo_evento - self.reloj
            self._actualizar_cronometros(delta)
            
            # 2. Mover reloj
            self.reloj = tiempo_evento
            
            # 3. Procesar Evento
            if tipo == "LLEGADA":
                # Crear cliente
                c = Cliente(len(self.historial_clientes) + len(self.cola_clientes), self.reloj)
                c.largo_cola_al_llegar = len(self.cola_clientes)
                
                ewt = self._calcular_ewt()
                self._gestionar_escalado(ewt)
                
                self.cola_clientes.append(c)
                self._intentar_asignar()
                self._programar_llegada()
                self._registrar_estado()
                
            elif tipo == "SALIDA":
                srv_id = data
                srv = self.servidores[srv_id]
                srv.ocupado = False
                
                self._intentar_asignar()
                if not self.cola_clientes: self._gestionar_escalado(0.0)
                self._registrar_estado()
            
            # UI
            if random.random() < 0.1: # Optimización visual
                progress_bar.progress(min(self.reloj / 8.0, 1.0))

        progress_bar.empty()
        return self._procesar_datos_finales()

    def _programar_llegada(self):
        tasa = self._get_tasa_actual()
        if tasa <= 0: return
        tiempo = random.expovariate(tasa)
        heapq.heappush(self.eventos, (self.reloj + tiempo, "LLEGADA", None))

    def _intentar_asignar(self):
        if not self.cola_clientes: return
        
        candidato = next((s for s in self.servidores if s.activo and not s.ocupado), None)
        if candidato:
            cliente = self.cola_clientes.popleft()
            candidato.ocupado = True
            
            cliente.hora_inicio_atencion = self.reloj
            duracion = random.expovariate(self.mu)
            cliente.hora_salida = self.reloj + duracion
            
            # Registrar tiempo trabajado
            candidato.tiempo_acumulado_trabajando += duracion
            
            self.historial_clientes.append(cliente)
            heapq.heappush(self.eventos, (cliente.hora_salida, "SALIDA", candidato.id))

    def _procesar_datos_finales(self):
        # 1. Dataframe Clientes (Base para el cálculo real)
        data_c = []
        for c in self.historial_clientes:
            wait = (c.hora_inicio_atencion - c.hora_llegada) * 60
            data_c.append({
                "Llegada_Raw": c.hora_llegada, # Float hours
                "Espera_Real_Min": wait,
                "Cola_Llegar": c.largo_cola_al_llegar
            })
        df_clientes = pd.DataFrame(data_c)
        
        # 2. Dataframe Sistema (Logs)
        df_log = pd.DataFrame(self.log_sistema)
        
        # 3. Dataframe Servidores (Utilización Real)
        data_s = []
        for s in self.servidores:
            # Utilización = Tiempo Trabajando / Tiempo Activo (Disponible)
            if s.tiempo_acumulado_activo > 0.001:
                util = (s.tiempo_acumulado_trabajando / s.tiempo_acumulado_activo) * 100
            else:
                util = 0.0
            
            data_s.append({
                "ID": f"Cajero {s.id}",
                "Horas_Activo": s.tiempo_acumulado_activo,
                "Horas_Trabajadas": s.tiempo_acumulado_trabajando,
                "Utilizacion_Pct": util
            })
        df_servidores = pd.DataFrame(data_s)
        
        return df_clientes, df_log, df_servidores

# ==========================================
# 2. GENERADOR DE DATASET PROFESIONAL (ETL)
# ==========================================

def generar_dataset_comparativo(df_log, df_clientes):
    """
    Combina el log del sistema con los tiempos reales de los clientes
    para comparar Estimación vs Realidad.
    """
    # 1. Preparar Logs de Sistema (Resamplear a 1 min)
    start_time = pd.Timestamp("2023-01-01 08:00:00")
    df_log['datetime'] = start_time + pd.to_timedelta(df_log['Tiempo_Exacto'], unit='h')
    df_log = df_log.set_index('datetime')
    
    df_ts_system = df_log.resample('1T').agg({
        'Cola': 'last',
        'Servidores_Activos': 'last',
        'Wait_Time_Estimado': 'mean', # Promedio de lo que el sistema creía
        'Tiempo_Exacto': 'last' # Para mantener el eje X numérico
    }).fillna(method='ffill')

    # 2. Preparar Datos de Clientes (Resamplear llegada)
    # Calculamos el promedio de espera REAL de los clientes que llegaron en ese minuto
    df_clientes['datetime'] = start_time + pd.to_timedelta(df_clientes['Llegada_Raw'], unit='h')
    df_clientes = df_clientes.set_index('datetime')
    
    df_ts_real = df_clientes.resample('1T').agg({
        'Espera_Real_Min': 'mean' # Promedio real ex-post
    })
    
    # 3. MERGE (Unión)
    df_final = df_ts_system.join(df_ts_real)
    
    # Rellenar vacíos: Si nadie llegó en un minuto, la espera real se asume 
    # similar a la anterior o 0 (aquí usaremos interpolación para suavizar gráficos)
    df_final['Espera_Real_Min'] = df_final['Espera_Real_Min'].interpolate(method='linear')
    
    return df_final

# ==========================================
# 3. INTERFAZ GRÁFICA (STREAMLIT)
# ==========================================

st.set_page_config(page_title="Simulador Bancario Final", layout="wide")
st.title("🏦 Dashboard de Operaciones: Realidad vs Estimación")

with st.sidebar:
    st.header("🎛️ Parámetros")
    TASA_BASE = st.slider("Demanda Base", 50, 300, 150)
    MAX_SERVERS = st.slider("Flota Máxima", 5, 25, 12)
    # Parametros para forzar que los servidores queden prendidos un poco mas y baje la utilización
    st.info("Para bajar la utilización del 100%, reduce el umbral de apagado.")
    UMBRAL_DOWN = st.slider("Apagar si espera < (min)", 0.5, 10.0, 2.0)
    
    if st.button("🚀 Ejecutar Simulación", type="primary"):
        sim = SimulacionFinal(TASA_BASE, 25, 1, MAX_SERVERS, 15.0, UMBRAL_DOWN)
        with st.spinner("Calculando series de tiempo..."):
            df_cl, df_lg, df_sv = sim.correr()
            df_dataset = generar_dataset_comparativo(df_lg, df_cl)
        
        st.session_state['data'] = (df_cl, df_sv, df_dataset)

# Verificar si hay datos
if 'data' in st.session_state:
    df_clientes, df_servidores, df_dataset = st.session_state['data']

    # --- TABLERO PRINCIPAL ---
    tab1, tab2, tab3 = st.tabs(["📊 Análisis Comparativo", "👷 Eficiencia Real", "💾 Dataset Final"])
    
    with tab1:
        st.subheader("La Mentira de los Promedios: Estimado vs Real")
        st.markdown("""
        El **Área Azul** es lo que el sistema *pensaba* que tardaría (Teórico).
        La **Línea Roja** es lo que *realmente* esperaron los clientes.
        *Nota cómo en la Hora Pico, la realidad suele superar a la estimación debido a la varianza acumulada.*
        """)
        
        fig = go.Figure()
        
        # Estimado
        fig.add_trace(go.Scatter(
            x=df_dataset.index, y=df_dataset['Wait_Time_Estimado'],
            name="Tiempo Estimado (Algoritmo)", fill='tozeroy', 
            line=dict(color='rgba(0, 100, 255, 0.3)', width=1)
        ))
        
        # Real
        fig.add_trace(go.Scatter(
            x=df_dataset.index, y=df_dataset['Espera_Real_Min'],
            name="Tiempo Real Sufrido (Ex-Post)", 
            line=dict(color='red', width=2)
        ))
        
        fig.update_layout(height=450, yaxis_title="Minutos de Espera")
        st.plotly_chart(fig, use_container_width=True)
        
        # Métricas de Error
        error = (df_dataset['Espera_Real_Min'] - df_dataset['Wait_Time_Estimado']).mean()
        st.caption(f"Sesgo promedio del algoritmo: {error:.2f} minutos (Si es positivo, el algoritmo subestima la espera).")

    with tab2:
        st.subheader("Utilización Real del Personal")
        st.markdown("Ahora el cálculo incluye el tiempo 'ocioso' mientras el cajero estaba activo esperando clientes.")
        
        # Filtramos cajeros que trabajaron algo
        df_srv_active = df_servidores[df_servidores['Horas_Activo'] > 0.1]
        
        fig_bar = px.bar(df_srv_active, x="ID", y="Utilizacion_Pct",
                         color="Utilizacion_Pct", color_continuous_scale="RdYlGn_r",
                         range_y=[0, 105], text_auto='.1f',
                         title="Porcentaje de Ocupación por Cajero")
        
        fig_bar.add_hline(y=100, line_dash="dot", line_color="gray")
        st.plotly_chart(fig_bar, use_container_width=True)
        
        st.write("Datos detallados:")
        st.dataframe(df_srv_active.style.format({"Horas_Activo": "{:.2f}", "Horas_Trabajadas": "{:.2f}", "Utilizacion_Pct": "{:.1f}%"}))

    with tab3:
        st.subheader("Dataset para Data Science (Kaggle Ready)")
        st.dataframe(df_dataset.head(10))
        
        csv = df_dataset.to_csv().encode('utf-8')
        st.download_button("📥 Descargar CSV Completo", csv, "simulacion_banco_real.csv", "text/csv")
else:
    st.info("Configura y ejecuta la simulación.")
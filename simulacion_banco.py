import heapq
import random
from collections import deque
import math

# --- ESTRUCTURAS DE DATOS ---

class Cliente:
    def __init__(self, id, hora_llegada):
        self.id = id
        self.hora_llegada = hora_llegada
        self.hora_inicio_atencion = None
        self.hora_salida = None
        
        # Métricas clave solicitadas
        self.largo_cola_al_llegar = 0      # Momento A
        self.largo_cola_al_entrar = 0      # Momento B
        self.ewt_al_llegar = 0.0           # Estimación del sistema

class Servidor:
    def __init__(self, id):
        self.id = id
        self.activo = False      # ¿Está encendido? (Shift activo)
        self.ocupado = False     # ¿Está atendiendo a alguien ahora?
        self.tiempo_fin_servicio = 0.0 # Cuándo termina la tarea actual

# --- MOTOR DE SIMULACIÓN ---

class SimulacionBancoInteligente:
    def __init__(self, 
                 tasa_llegada_hora, 
                 tasa_servicio_hora, 
                 min_servidores=1, 
                 max_servidores=10,
                 umbral_activar_min=15.0,   # Si espera > 15 min -> Activar
                 umbral_desactivar_min=5.0  # Si espera < 5 min -> Desactivar
                 ):
        
        # Parámetros (No hardcodeados)
        self.lambd = tasa_llegada_hora
        self.mu = tasa_servicio_hora
        self.min_servers = min_servidores
        self.max_servers = max_servidores
        self.umbral_up = umbral_activar_min / 60.0   # Convertir a horas
        self.umbral_down = umbral_desactivar_min / 60.0 # Convertir a horas
        
        # Estado del Sistema
        self.reloj = 0.0
        self.cola_clientes = deque()
        self.servidores = [Servidor(i) for i in range(max_servidores)]
        
        # Inicializar servidores mínimos
        for i in range(min_servidores):
            self.servidores[i].activo = True
            
        # Cola de Eventos (Priority Queue)
        # Tuplas: (tiempo, tipo_evento, data)
        self.eventos = []
        
        # Estadísticas
        self.historial_clientes = []
        self.log_cambios_servidores = [] # Para saber cuándo se activaron/desactivaron

    def _calcular_ewt(self):
        """Calcula el Estimated Wait Time (Tiempo Estimado de Espera)"""
        # Contamos servidores activos
        activos = sum(1 for s in self.servidores if s.activo)
        largo_cola = len(self.cola_clientes)
        
        if activos == 0: return 9999.0 # Evitar división por cero (no debería pasar)
        
        # Fórmula: Personas delante / (Velocidad combinada de los servidores)
        # Tasa combinada = activos * mu
        ewt_horas = largo_cola / (activos * self.mu)
        return ewt_horas

    def _gestionar_escalado(self, ewt_actual):
        """El CEREBRO: Decide si encender o apagar servidores"""
        activos = sum(1 for s in self.servidores if s.activo)
        
        # REGLA 1: Activar si la espera es muy alta
        if ewt_actual > self.umbral_up and activos < self.max_servers:
            # Buscar un servidor inactivo y activarlo
            for s in self.servidores:
                if not s.activo:
                    s.activo = True
                    self.log_cambios_servidores.append((self.reloj, "ACTIVAR", s.id, ewt_actual*60))
                    # print(f"[{self.reloj:.2f}] 🚨 ALERTA: EWT {ewt_actual*60:.1f}min. Activando Servidor {s.id}")
                    return # Solo activamos uno por vez
        
        # REGLA 2: Desactivar si el sistema está muy holgado (Histéresis)
        elif ewt_actual < self.umbral_down and activos > self.min_servers:
            # Solo desactivamos si hay servidores OCIOSOS (no vamos a echar a un cajero mientras atiende)
            # Buscamos el servidor activo con ID más alto (LIFO) que esté libre
            for i in range(self.max_servers - 1, -1, -1):
                s = self.servidores[i]
                if s.activo and not s.ocupado:
                    s.activo = False
                    self.log_cambios_servidores.append((self.reloj, "DESACTIVAR", s.id, ewt_actual*60))
                    # print(f"[{self.reloj:.2f}] 💤 RELAX: EWT {ewt_actual*60:.1f}min. Desactivando Servidor {s.id}")
                    return

    def programar_llegada(self):
        # Generar próxima llegada (distribución exponencial)
        tiempo_hasta_proximo = random.expovariate(self.lambd)
        proxima_llegada = self.reloj + tiempo_hasta_proximo
        heapq.heappush(self.eventos, (proxima_llegada, "LLEGADA", None))

    def correr(self, num_clientes_a_simular):
        print(f"🚀 Iniciando simulación para {num_clientes_a_simular} clientes...")
        
        # Primer evento: Llega el primer cliente
        self.programar_llegada()
        
        clientes_procesados = 0
        cliente_id_counter = 0

        while clientes_procesados < num_clientes_a_simular or len(self.eventos) > 0:
            if not self.eventos: break
            
            # Sacar el evento más próximo
            tiempo_evento, tipo, data = heapq.heappop(self.eventos)
            self.reloj = tiempo_evento
            
            # --- MANEJO DE EVENTO: LLEGADA ---
            if tipo == "LLEGADA":
                if cliente_id_counter < num_clientes_a_simular:
                    cliente = Cliente(cliente_id_counter, self.reloj)
                    cliente_id_counter += 1
                    
                    # 1. Medir Momento A (Cola al llegar)
                    cliente.largo_cola_al_llegar = len(self.cola_clientes)
                    
                    # 2. Calcular EWT y Gestionar Servidores
                    ewt = self._calcular_ewt()
                    cliente.ewt_al_llegar = ewt
                    self._gestionar_escalado(ewt)
                    
                    # 3. Encolar
                    self.cola_clientes.append(cliente)
                    
                    # 4. Intentar asignar servicio inmediatamente si hay hueco
                    self._intentar_asignar_servicio()
                    
                    # 5. Programar siguiente llegada
                    self.programar_llegada()

            # --- MANEJO DE EVENTO: SALIDA (Fin de Servicio) ---
            elif tipo == "SALIDA":
                servidor_id = data
                servidor = self.servidores[servidor_id]
                servidor.ocupado = False
                clientes_procesados += 1
                
                # Al liberarse un servidor, intentamos tomar a alguien de la cola
                atendio_a_alguien = self._intentar_asignar_servicio()
                
                if not atendio_a_alguien:
                    # Si no hay nadie en cola, evaluamos si sobran servidores
                    # (Porque el EWT será 0)
                    self._gestionar_escalado(0.0)

    def _intentar_asignar_servicio(self):
        """Busca servidor libre y cliente en espera"""
        if not self.cola_clientes:
            return False
            
        # Buscar primer servidor activo y no ocupado
        candidato = None
        for s in self.servidores:
            if s.activo and not s.ocupado:
                candidato = s
                break
        
        if candidato:
            # Sacamos cliente de la cola
            cliente = self.cola_clientes.popleft()
            
            # 1. Medir Momento B (Cola al entrar a servicio)
            # Nota: Él ya salió, así que medimos la cola actual (los que quedan atrás)
            cliente.largo_cola_al_entrar = len(self.cola_clientes)
            
            # 2. Asignar
            candidato.ocupado = True
            cliente.hora_inicio_atencion = self.reloj
            
            # Generar tiempo de servicio
            duracion = random.expovariate(self.mu)
            cliente.hora_salida = self.reloj + duracion
            candidato.tiempo_fin_servicio = cliente.hora_salida
            
            # Guardar cliente finalizado
            self.historial_clientes.append(cliente)
            
            # Programar evento de salida
            heapq.heappush(self.eventos, (cliente.hora_salida, "SALIDA", candidato.id))
            return True
            
        return False

# --- ZONA DE PRUEBAS ---

if __name__ == "__main__":
    # Escenario de estrés:
    # Llegan 100/hora. Cada servidor atiende 15/hora.
    # 1 Servidor es insuficiente (15 < 100). Necesitaremos aprox 7 servidores (7*15=105) para estabilizar.
    # El sistema debería empezar con 1 y subir automáticamente hasta 7 u 8.
    
    sim = SimulacionBancoInteligente(
        tasa_llegada_hora=100.0, 
        tasa_servicio_hora=15.0,
        min_servidores=1,
        max_servidores=10,
        umbral_activar_min=15.0, # Si espero mas de 15 min, contrata gente
        umbral_desactivar_min=5.0
    )
    
    sim.correr(5000) # Simular 5000 clientes
    
    # --- RESULTADOS ---
    print("-" * 50)
    print("📊 RESULTADOS FINALES")
    
    clientes = sim.historial_clientes
    tiempos_espera = [(c.hora_inicio_atencion - c.hora_llegada)*60 for c in clientes]
    promedio = sum(tiempos_espera) / len(tiempos_espera)
    maximo = max(tiempos_espera)
    
    print(f"Tiempo promedio de espera real: {promedio:.2f} min")
    print(f"Tiempo máximo de espera sufrido: {maximo:.2f} min")
    
    # Análisis de Escalado
    cambios = sim.log_cambios_servidores
    activaciones = [c for c in cambios if c[1] == "ACTIVAR"]
    desactivaciones = [c for c in cambios if c[1] == "DESACTIVAR"]
    
    print(f"Total de activaciones de cajeros: {len(activaciones)}")
    print(f"Total de desactivaciones (ahorro): {len(desactivaciones)}")
    
    # Verificación de los últimos clientes
    print("\n🔍 Muestra de los últimos 5 clientes:")
    print("ID | Llegada | Cola(Llegada) | Cola(Entrada) | Espera Real")
    for c in clientes[-5:]:
        espera = (c.hora_inicio_atencion - c.hora_llegada)*60
        print(f"{c.id:4} | {c.hora_llegada:7.2f} | {c.largo_cola_al_llegar:13} | {c.largo_cola_al_entrar:13} | {espera:6.2f} min")
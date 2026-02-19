#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <vector>
#include <random>
#include <numeric>
#include <algorithm>

namespace py = pybind11;

// 1. Estructura para devolver los resultados ordenados a Python
struct SimResult {
    double tiempo_promedio_espera;
    double tiempo_promedio_sistema;
    double utilizacion_servidor;
    int clientes_totales;
    // Devolvemos una muestra de los primeros 1000 tiempos para graficar en Python
    std::vector<double> tiempos_espera_muestra; 
};

// 2. La Clase Simulador
class SimuladorMM1 {
public:
    SimuladorMM1(double tasa_llegada, double tasa_servicio) 
        : lambda(tasa_llegada), mu(tasa_servicio) {
            // Inicializar generador de números aleatorios (Mersenne Twister)
            rng.seed(std::random_device{}());
        }

    SimResult correr(int n_clientes) {
        std::vector<double> esperas;
        esperas.reserve(n_clientes);
        
        // Distribuciones exponenciales (estándar en teoría de colas)
        std::exponential_distribution<double> dist_llegada(lambda);
        std::exponential_distribution<double> dist_servicio(mu);

        double reloj_actual = 0.0;
        double momento_servidor_libre = 0.0;
        double suma_esperas = 0.0;
        double suma_tiempo_sistema = 0.0;
        double tiempo_total_servicio = 0.0;

        for (int i = 0; i < n_clientes; ++i) {
            // 1. Generar tiempo hasta el próximo cliente y tiempo que tardará en ser atendido
            double tiempo_interllegada = dist_llegada(rng);
            double duracion_servicio = dist_servicio(rng);

            // 2. Avanzar el reloj
            reloj_actual += tiempo_interllegada;

            // 3. Calcular tiempos
            // El servicio comienza cuando llega el cliente O cuando el servidor se libera (lo que pase último)
            double inicio_servicio = std::max(reloj_actual, momento_servidor_libre);
            
            double tiempo_espera = inicio_servicio - reloj_actual;
            double tiempo_sistema = tiempo_espera + duracion_servicio;
            
            // 4. Actualizar estado
            momento_servidor_libre = inicio_servicio + duracion_servicio;
            tiempo_total_servicio += duracion_servicio;

            // 5. Guardar estadísticas
            suma_esperas += tiempo_espera;
            suma_tiempo_sistema += tiempo_sistema;
            
            // Guardamos todos los datos (o solo una muestra si son demasiados)
            if (i < 5000) { // Solo guardamos los primeros 5000 para graficar y no saturar RAM
                esperas.push_back(tiempo_espera);
            }
        }

        // Construir resultado
        SimResult res;
        res.clientes_totales = n_clientes;
        res.tiempo_promedio_espera = suma_esperas / n_clientes;
        res.tiempo_promedio_sistema = suma_tiempo_sistema / n_clientes;
        // La simulación termina cuando el último cliente sale
        res.utilizacion_servidor = tiempo_total_servicio / momento_servidor_libre; 
        res.tiempos_espera_muestra = esperas;

        return res;
    }

private:
    double lambda; // Clientes por minuto
    double mu;     // Clientes atendidos por minuto
    std::mt19937 rng; // Generador aleatorio eficiente
};

// 3. El Binding (Conectar C++ con Python)
PYBIND11_MODULE(super_cpp, m) {
    m.doc() = "Módulo de Simulación de Colas M/M/1";

    // Exponer la struct SimResult para que Python pueda leer sus campos
    py::class_<SimResult>(m, "SimResult")
        .def_readonly("avg_wait", &SimResult::tiempo_promedio_espera)
        .def_readonly("avg_sys", &SimResult::tiempo_promedio_sistema)
        .def_readonly("utilization", &SimResult::utilizacion_servidor)
        .def_readonly("total_customers", &SimResult::clientes_totales)
        .def_readonly("wait_samples", &SimResult::tiempos_espera_muestra);

    // Exponer la clase SimuladorMM1
    py::class_<SimuladorMM1>(m, "Simulador")
        .def(py::init<double, double>()) // Constructor
        .def("correr", &SimuladorMM1::correr); // Método
}
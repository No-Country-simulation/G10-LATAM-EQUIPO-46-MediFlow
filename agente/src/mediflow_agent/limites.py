"""Control de ritmo para no pasarse del limite gratuito del modelo.

La capa gratuita de Gemini limita **por minuto**, no solo por dia. Para
`gemini-3.5-flash-lite` el tope son 15 pedidos por minuto. Un triaje suelto
nunca lo alcanza, pero evaluar los 30 documentos del corpus son 60 llamadas
seguidas y choca contra el limite en los primeros segundos.

El sintoma es un 429 con `RetryInfo`, y reintentar sin esperar lo empeora:
cada reintento tambien cuenta. Lo correcto es no pasarse.

Este limitador no reintenta ni atrapa errores: solo espera lo necesario antes
de dejar pasar la siguiente llamada. Es deliberadamente simple.
"""

import threading
import time

from mediflow_agent.config import ajuste

# Tope de la capa gratuita para los modelos flash-lite. Se puede subir con
# MEDIFLOW_RPM cuando el proyecto tenga una clave de pago.
PEDIDOS_POR_MINUTO = int(
    ajuste("rendimiento", "pedidos_por_minuto", 15, "MEDIFLOW_RPM")
)


class LimitadorDeRitmo:
    """Deja pasar como mucho N llamadas por minuto.

    Lleva las marcas de tiempo de las llamadas del ultimo minuto y, cuando ya
    hay N, espera hasta que la mas vieja cumpla el minuto.

    Es seguro entre hilos: el servicio de triaje corre el clasificador y el
    extractor desde un ThreadPoolExecutor.
    """

    def __init__(self, pedidos_por_minuto: int = PEDIDOS_POR_MINUTO):
        if pedidos_por_minuto < 1:
            raise ValueError("El limite tiene que ser al menos 1 por minuto.")

        self._tope = pedidos_por_minuto
        self._marcas: list[float] = []
        self._candado = threading.Lock()

    def esperar_turno(self) -> float:
        """Bloquea hasta que se pueda hacer otra llamada.

        Devuelve cuantos segundos espero, para poder informarlo.
        """
        with self._candado:
            ahora = time.monotonic()

            # Se descartan las marcas de hace mas de un minuto.
            self._marcas = [m for m in self._marcas if ahora - m < 60.0]

            if len(self._marcas) < self._tope:
                self._marcas.append(ahora)
                return 0.0

            # Hay que esperar a que la mas vieja cumpla el minuto. Se suma un
            # margen chico porque el reloj del servidor no es el nuestro.
            espera = 60.0 - (ahora - self._marcas[0]) + 0.5

        time.sleep(espera)

        with self._candado:
            self._marcas = [m for m in self._marcas if time.monotonic() - m < 60.0]
            self._marcas.append(time.monotonic())

        return espera

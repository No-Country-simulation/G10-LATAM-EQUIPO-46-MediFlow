# Despliegue en OCI Compute

Pone la página de MediFlow en internet, con un enlace público, usando una
máquina **Always Free** de Oracle Cloud. Es el recurso opcional que el
enunciado lista como diferencial:

> **Despliegue Completo en la Nube (OCI Compute):** alojamiento de la
> aplicación en una máquina virtual Always Free de OCI con acceso público.

Toma entre 40 y 60 minutos la primera vez.

---

## Antes de empezar, leé esto

**La página va a quedar abierta a internet sin contraseña.** Cualquiera con el
enlace puede procesar documentos, y eso significa dos cosas concretas:

- **Gasta tu cuota de Gemini.** El límite gratuito es 15 pedidos por minuto y
  tiene tope diario. Alguien que pruebe veinte documentos te deja sin cuota
  para la demo.
- **Escribe en el bucket de OCI.** Los objetos que cree quedan ahí, y por PAR
  no se pueden borrar desde la aplicación.

Para una demo de hackathon es un riesgo aceptable, pero **rotá la clave de
Gemini y el PAR después de la entrega**, y no publiques el enlace más allá del
equipo y el jurado hasta ese momento.

---

## 1. Crear la máquina

En la consola de OCI: **Compute → Instances → Create instance**.

| Campo | Qué poner |
|-------|-----------|
| Name | `mediflow` |
| Image | **Canonical Ubuntu 24.04** |
| Shape | **VM.Standard.A1.Flex** con 1 OCPU y 6 GB |
| Networking | Subred pública, **Assign a public IPv4 address: Yes** |
| SSH keys | Generar y **descargar la clave privada** |

Dos advertencias que cuestan tiempo si se pasan por alto:

- **La forma tiene que decir "Always Free Eligible".** Si elegís otra, la
  instancia se cobra. Las `A1.Flex` de ARM son las del plan gratuito; si OCI
  dice que no hay capacidad en tu región, probá con `VM.Standard.E2.1.Micro`,
  que también es gratuita.
- **La clave privada se descarga una sola vez.** Si cerrás esa pantalla sin
  bajarla, hay que recrear la instancia.

Anotá la **IP pública** que aparece al terminar.

## 2. Abrir el puerto 80

Por defecto OCI bloquea todo. Hay que abrirlo en dos lugares, y olvidarse del
segundo es el error más común:

**En la red:** Networking → Virtual Cloud Networks → tu VCN → Security Lists →
**Add Ingress Rule**:

| Campo | Valor |
|-------|-------|
| Source CIDR | `0.0.0.0/0` |
| IP Protocol | TCP |
| Destination Port Range | `80` |

**En la máquina**, una vez dentro por SSH (paso 3):

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo netfilter-persistent save
```

Ubuntu en OCI trae su propio cortafuegos además del de la nube. Si solo abrís
la regla de red, el puerto sigue cerrado y el síntoma es que el navegador
queda cargando para siempre, sin error.

## 3. Entrar y preparar la máquina

```bash
chmod 400 tu-clave.key
ssh -i tu-clave.key ubuntu@LA_IP_PUBLICA
```

Ya dentro:

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu
exit
```

Hay que volver a entrar para que el grupo `docker` tenga efecto.

## 4. Traer el proyecto y configurarlo

```bash
ssh -i tu-clave.key ubuntu@LA_IP_PUBLICA

git clone https://github.com/No-Country-simulation/G10-LATAM-EQUIPO-46-MediFlow.git
cd G10-LATAM-EQUIPO-46-MediFlow

cp agente/.env.example agente/.env
nano agente/.env
```

Completá como mínimo:

```env
GEMINI_API_KEY=tu-clave
GEMINI_MODEL=gemini-3.5-flash-lite
MEDIFLOW_ALMACEN=par
MEDIFLOW_OCI_PAR=https://objectstorage.sa-saopaulo-1.oraclecloud.com/p/.../o/
MEDIFLOW_BUCKET=bucket-hackaton-01
```

> El `.env` se crea **en la máquina** y nunca se sube al repositorio. El
> `.gitignore` lo bloquea, pero conviene saber por qué está bloqueado.

## 5. Levantar

```bash
docker compose -f infrastructure/docker-compose.yml up -d --build
```

La primera construcción tarda varios minutos: el SDK de OCI y LangChain son
pesados y la máquina gratuita no es rápida.

Comprobar que arrancó:

```bash
docker compose -f infrastructure/docker-compose.yml ps
curl -s localhost/salud
```

Tiene que responder `{"status":"ok","servicio":"mediflow-triaje"}`.

## 6. El enlace

```
http://LA_IP_PUBLICA
```

Ese es el enlace público que va en la tabla *Enlaces del proyecto* del README,
en el campo **Despliegue**.

---

## Operación

```bash
# Ver qué está pasando
docker compose -f infrastructure/docker-compose.yml logs -f --tail 50

# Actualizar tras un merge en main
git pull && docker compose -f infrastructure/docker-compose.yml up -d --build

# Reiniciar
docker compose -f infrastructure/docker-compose.yml restart

# Apagar
docker compose -f infrastructure/docker-compose.yml down
```

El contenedor tiene `restart: unless-stopped`: si la máquina se reinicia, la
página vuelve sola. Sin eso, un reinicio de la instancia dejaría el enlace
caído sin que nadie se entere hasta que alguien lo abra.

## Cuando algo no anda

| Síntoma | Causa casi siempre |
|---------|--------------------|
| El navegador queda cargando, sin error | Falta la regla de `iptables` dentro de la máquina (paso 2) |
| `connection refused` | El contenedor no está levantado: `docker compose ps` |
| La página carga pero triar da error 500 | Falta `GEMINI_API_KEY` en el `.env` de la máquina |
| Respuestas de 40 segundos | Cuota de Gemini: 15 pedidos por minuto |
| `status_backup: "fallo"` | El PAR venció o está mal copiado |

Los logs dicen cuál es:

```bash
docker compose -f infrastructure/docker-compose.yml logs --tail 100
```

## Si la imagen no construye por falta de memoria

Una `E2.1.Micro` tiene 1 GB y `pip` puede quedarse sin memoria. Agregar
intercambio lo resuelve:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Sobre HTTPS

Queda en `http://`, sin certificado. Para tenerlo hace falta un dominio, y una
IP pelada no sirve: las autoridades de certificación no emiten certificados
para direcciones IP. Si consiguen un dominio gratuito, con Caddy son diez
minutos más. Para la demo, `http://` alcanza.

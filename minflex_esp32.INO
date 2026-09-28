#include <WiFi.h>

// ---------------- CONFIGURA EL AP ----------------
const char* AP_SSID     = "ESP32_EEG";
const char* AP_PASSWORD = "eeg12345";   // minimo 8 caracteres
const uint16_t TCP_PORT = 1234;
// ---------------------------------------------------

// Encabezado que espera receptor_mindflex.py (sin "raw")
const char* CSV_HEADER =
  "timestamp_ms,signal_quality,attention,meditation,blink,"
  "delta,theta,alpha_low,alpha_high,beta_low,beta_high,gamma_low,gamma_mid\n";

HardwareSerial MindFlexSerial(2); // UART2: RX2=GPIO16, TX2=GPIO17 (no se usa TX)
WiFiServer server(TCP_PORT);
WiFiClient client;
bool headerSentToCurrentClient = false;

// ---------------- Parser de paquetes TGAM ----------------
enum ParseState { WAIT_SYNC1, WAIT_SYNC2, WAIT_PLENGTH, READ_PAYLOAD, READ_CHECKSUM };
ParseState state = WAIT_SYNC1;

uint8_t payload[256];
uint8_t payloadLength = 0;
uint8_t payloadIndex = 0;
uint8_t checksumSum = 0;

int signalQuality = -1;
int attention  = -1;
int meditation = -1;
int blink      = -1; // -1 = sin evento en este paquete
long delta = -1, theta = -1, alphaLow = -1, alphaHigh = -1;
long betaLow = -1, betaHigh = -1, gammaLow = -1, gammaMid = -1;
bool havePowerBands = false;

void resetPacketValues() {
  signalQuality = attention = meditation = -1;
  blink = -1;
  delta = theta = alphaLow = alphaHigh = -1;
  betaLow = betaHigh = gammaLow = gammaMid = -1;
  havePowerBands = false;
}

void startAP() {
  WiFi.softAP(AP_SSID, AP_PASSWORD);
  Serial.print("Access Point iniciado. SSID: ");
  Serial.println(AP_SSID);
  Serial.print("IP del ESP32: ");
  Serial.println(WiFi.softAPIP()); // normalmente 192.168.4.1
  Serial.print("Puerto TCP: ");
  Serial.println(TCP_PORT);
}

void sendLineToClient() {
  if (!client || !client.connected()) return;

  if (!headerSentToCurrentClient) {
    client.print(CSV_HEADER);
    headerSentToCurrentClient = true;
  }

  if (!havePowerBands && attention < 0 && meditation < 0 && blink < 0) return;

  String line = String(millis()) + "," +
                String(signalQuality) + "," +
                String(attention) + "," +
                String(meditation) + "," +
                String(blink) + "," +
                String(delta) + "," +
                String(theta) + "," +
                String(alphaLow) + "," +
                String(alphaHigh) + "," +
                String(betaLow) + "," +
                String(betaHigh) + "," +
                String(gammaLow) + "," +
                String(gammaMid) + "\n";

  client.print(line);
}

void parsePayload() {
  resetPacketValues();
  uint8_t i = 0;
  while (i < payloadLength) {
    uint8_t code = payload[i];

    if (code == 0x02) {               // POOR_SIGNAL quality
      signalQuality = payload[i + 1];
      i += 2;
    } else if (code == 0x04) {        // Attention (eSense)
      attention = payload[i + 1];
      i += 2;
    } else if (code == 0x05) {        // Meditation (eSense)
      meditation = payload[i + 1];
      i += 2;
    } else if (code == 0x16) {        // Blink strength
      blink = payload[i + 1];
      i += 2;
    } else if (code == 0x83) {        // ASIC EEG Power (8 bandas x 3 bytes)
      uint8_t base = i + 2;
      delta     = ((long)payload[base + 0]  << 16) | ((long)payload[base + 1]  << 8) | payload[base + 2];
      theta     = ((long)payload[base + 3]  << 16) | ((long)payload[base + 4]  << 8) | payload[base + 5];
      alphaLow  = ((long)payload[base + 6]  << 16) | ((long)payload[base + 7]  << 8) | payload[base + 8];
      alphaHigh = ((long)payload[base + 9]  << 16) | ((long)payload[base + 10] << 8) | payload[base + 11];
      betaLow   = ((long)payload[base + 12] << 16) | ((long)payload[base + 13] << 8) | payload[base + 14];
      betaHigh  = ((long)payload[base + 15] << 16) | ((long)payload[base + 16] << 8) | payload[base + 17];
      gammaLow  = ((long)payload[base + 18] << 16) | ((long)payload[base + 19] << 8) | payload[base + 20];
      gammaMid  = ((long)payload[base + 21] << 16) | ((long)payload[base + 22] << 8) | payload[base + 23];
      havePowerBands = true;
      i += 26; // 1 (code) + 1 (longitud) + 24 (datos)
    } else {
      // Codigo desconocido o no usado (ej. 0x80 RAW EEG, que este MindFlex
      // no envia): avanzamos de forma segura sin intentar interpretarlo.
      i += 1;
    }
  }

  sendLineToClient();
}

void readMindFlex() {
  while (MindFlexSerial.available()) {
    uint8_t b = MindFlexSerial.read();

    switch (state) {
      case WAIT_SYNC1:
        if (b == 0xAA) state = WAIT_SYNC2;
        break;

      case WAIT_SYNC2:
        state = (b == 0xAA) ? WAIT_PLENGTH : WAIT_SYNC1;
        break;

      case WAIT_PLENGTH:
        if (b == 0xAA) break;
        if (b > 170) { state = WAIT_SYNC1; break; }
        payloadLength = b;
        payloadIndex = 0;
        checksumSum = 0;
        state = READ_PAYLOAD;
        break;

      case READ_PAYLOAD:
        payload[payloadIndex++] = b;
        checksumSum += b;
        if (payloadIndex >= payloadLength) state = READ_CHECKSUM;
        break;

      case READ_CHECKSUM: {
        uint8_t checksum = 0xFF - (checksumSum & 0xFF);
        if (checksum == b) {
          parsePayload();
        }
        state = WAIT_SYNC1;
        break;
      }
    }
  }
}

void handleClientConnection() {
  if (!client || !client.connected()) {
    WiFiClient newClient = server.available();
    if (newClient) {
      client = newClient;
      headerSentToCurrentClient = false;
      Serial.println("Cliente Python conectado.");
    }
  }
}

void setup() {
  Serial.begin(115200);
  MindFlexSerial.begin(9600, SERIAL_8N1, 16, 17); // RX2=16, TX2=17

  startAP();
  server.begin();
  Serial.println("Servidor TCP iniciado. Esperando conexion de Python...");
}

void loop() {
  handleClientConnection();
  readMindFlex();
}

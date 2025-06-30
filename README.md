# 📸 Mobilní Fotopast s ESP32, LTE a nízkou spotřebou

Tato diplomová práce řeší návrh, realizaci a testování **mobilní fotopasti**, která díky kombinaci **ESP32-S3**, **ESP32-C3**, **LTE modulu A7670E**, PIR senzoru, SD karty a úsporných spínacích obvodů umožňuje **dlouhodobý provoz v terénu** s minimální spotřebou energie.

---

## 🚩 Hlavní cíle projektu

✅ **Pořizování snímků** při detekci pohybu  
✅ **Odesílání dat** na vzdálený server přes LTE (HTTP POST)  
✅ **Přijímání SMS příkazů** (restart, foto, stav)  
✅ **Nízká klidová spotřeba** – ESP32-C3 řídí napájení hlavní části  
✅ **Konfigurovatelná přes USB i vzdáleně**  
✅ **Monitorování stavu baterie** přes INA219

---

## 🔋 Hardwarové komponenty

| Komponenta       | Popis | Napájení |
|------------------|-------|----------|
| **ESP32-S3 CAM** | Hlavní deska s kamerou OV5640, SD kartou | 5V |
| **ESP32-C3 (LaskaKit LPKit)** | Řídicí MCU s ultra nízkou spotřebou | 3.3V |
| **LTE modul A7670E** | Připojení na mobilní síť, SMS, GPS | 5V |
| **PIR senzor HC-SR501** | Detekce pohybu, wake-up signál | 5V |
| **INA219** | Sledování napětí a proudu akumulátoru | 5V |
| **Step-down měniče** | Regulace napětí z olověného 6V akumulátoru | 5V/3.3V |
| **Tranzistory (NPN BC337)** | Spínání napájení periferií | - |

---

## ⚡ Logika úspory energie

- **ESP32-C3** je hlavní „strážce“: řídí napájení ESP32-S3 a LTE modulu.
- **PIR senzor** zůstává aktivní a může kdykoli vzbudit ESP32-C3.
- **Step-down měniče** napájejí ESP32-C3 + PIR trvale, ostatní spíná tranzistor.
- **LTE modul** umí deep sleep (`AT+CSCLK=1`), nebo se zcela vypne.

---


---

## ⚙️ Základní funkce

- **Detekce pohybu** → Wake-up → Pořízení fotky → Odeslání na server
- **Probuzení časovačem** → Kontrola SMS příkazů → Změna konfigurace
- **Manuální wake-up tlačítkem** → Lokální konfigurace přes USB
- **Měření baterie** → Stav odešle SMS na požádání

---

## 📏 Typická spotřeba

| Režim | Odběr |
|-------|-------|
| Klid (ESP32-C3 + PIR) | 5–10 mA |
| LTE aktivní | 50–200 mA |
| Fotopast aktivní (kamera + SD + LTE) | až 300–400 mA (špička) |

---

## 📝 Konfigurace

- Parametry (URL, klíče, intervaly) se ukládají v **NVS**.
- Konfigurace probíhá buď přes **seriál** (USB) nebo **vzdáleně** (HTTP GET / SMS).

---

## 🔧 Jak spustit

1. Zapojit všechny moduly podle schématu.
2. Nahraj firmware do **ESP32-C3** i **ESP32-S3**.
3. Připoj napájení (6V olověný akumulátor).
4. Ověř wake-up přes PIR nebo tlačítko.
5. Sleduj výpis v **seriál konzoli**.
6. Testuj přenos na server, příjem SMS a funkci spánku.

---

## 💡 Autor

**Vladimír Skoumal**  
Diplomová práce VUT FEKT, 2025  
Kontakt: `xskoum01@gmail.com`

---

## ⚖️ Licence

Projekt je součástí studijní práce – určený **pro nekomerční výukové účely**.

---




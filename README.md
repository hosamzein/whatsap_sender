# whatsap_sender
I looked through your script **`whatsapp_sender - v16 latest.py`**, and here are the **structured features** that the app provides:

---

### 🔹 **Core Functions**

1. **Bulk WhatsApp Messaging**

   * Reads contacts from an **Excel file** (`.xlsx`).
   * Excel must include at least:

     * **Phone/Number** column.
     * **Message** column (optional if using custom text).
   * Sends messages using **pywhatkit**.

2. **Custom Message Templates**

   * Supports dynamic placeholders like `{{Name}}`, `{{Phone}}`, or any Excel column.
   * Normalizes phone numbers with a default or custom **country code**.

---

### 🔹 **Upload & Data Handling**

* Upload Excel file via UI.
* Automatically detects **Phone/Number** column.
* Previews uploaded contacts in a searchable table.
* Displays both raw and **normalized phone numbers**.
* Supports filtering/search by any field (Seq, Phone, Name, Message, etc.).
* Reset session to clear uploaded file and restart.

---

### 🔹 **Message Settings**

* Choose between:

  * **Message Column** (from Excel).
  * **Custom Text** (typed in app).
* Insert Excel column values into messages dynamically with placeholders.
* Variables panel lists available fields as quick-insert buttons.

---

### 🔹 **Controls for Sending**

* **Start**: begin sending messages in bulk.
* **Pause / Resume**: temporarily halt and continue sending.
* **Reset**: clear session and reset all progress.

---

### 🔹 **Timing Controls**

* **Country Code** input (default `+20`).
* **Wait time after opening chat** (default `20s`).
* **Delay between messages** (default `40s`).
* Prevents bans by spacing messages.

---

### 🔹 **Progress & Monitoring**

* Shows:

  * Progress bar.
  * % completed.
  * Number of processed contacts.
* Highlights the currently processed row in the contacts table.
* Displays completion dialog when done.

---

### 🔹 **Search & Filter**

* Search contacts by **any column**.
* Clear filter option resets to show all.
* Real-time updates with live background thread.

---

### 🔹 **User Interface**

* Built with **NiceGUI**:

  * Modern cards, inputs, and buttons.
  * Organized layout:

    * Upload & Settings.
    * Message Settings.
    * Controls.
    * Progress tracker.
    * Search & Filter.
    * Contacts Table.

---

✅ In short:
This app is a **WhatsApp bulk sender with Excel upload, dynamic templating, real-time progress, pause/resume, and a modern UI**.
Developer greeting : Hossam Zein
---

Do you want me to make you a **feature map diagram (flow chart)** to visualize all these structured features?


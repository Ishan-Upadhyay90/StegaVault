# 🔐 StegaVault – Advanced Steganography Web App

StegaVault is a powerful Flask-based steganography application that allows users to securely hide and extract text or files inside images using advanced techniques like LSB (Least Significant Bit) encoding and encryption algorithms.

This project is implemented as a single-file application for simplicity, portability, and ease of deployment.

---

## 🚀 Features

### 🔒 Text Steganography
- Hide secret messages inside images
- Extract hidden messages from images
- Supports encryption before embedding

### 📁 File Steganography
- Hide any file type (PDF, ZIP, Images, etc.)
- Extract files with original filename and structure
- Supports large files (up to 50MB depending on image capacity)

### 🔑 Encryption Support
- Caesar Cipher
- Vigenère Cipher
- Client-side + server-side processing

### 📊 Real-Time Progress Tracking
- Live encoding/decoding progress using Server-Sent Events (SSE)
- Smooth UI feedback for large file operations

### 🎨 Modern UI
- Responsive design using Bootstrap 5
- Clean and user-friendly interface
- Capacity indicators and warnings

---

## 🧠 How It Works

### 🖼️ LSB Steganography
Each pixel contains 3 color channels (RGB). The least significant bit of each channel is modified to store data, ensuring minimal visual distortion.

### 📦 File Encoding Process
1. Convert file into binary format  
2. Add metadata (filename + size)  
3. Embed binary data into image pixels  
4. Generate encoded image  

### 🔓 Decoding Process
1. Extract binary data from image  
2. Reconstruct metadata  
3. Recover original file/message  

---

## 🛠️ Tech Stack

- Backend: Python, Flask  
- Image Processing: OpenCV  
- Data Handling: NumPy, Struct  
- Frontend: HTML, CSS, JavaScript, Bootstrap  
- Real-time Updates: Server-Sent Events (SSE)  

---

## 📂 Project Structure

StegaVault/
│── app.py          # Main Flask application (single-file project)
│── uploads/        # Temporary storage (auto-created)

---

## ⚙️ Installation & Setup

1. Clone Repository
git clone https://github.com/Ishan-Upadhyay90/StegaVault.git  
cd StegaVault  

2. Install Dependencies
pip install flask opencv-python numpy werkzeug  

3. Run Application
python app.py  

4. Open in Browser
http://127.0.0.1:5000  

---

## ⚠️ Important Notes

- Maximum upload size: 50MB  
- Large files require high-resolution images  
- PNG format is recommended for better data retention  
- Avoid compressing encoded images (can corrupt data)  

---

## 🔐 Security Considerations

- This tool provides basic encryption + steganography  
- Not intended for military-grade security  
- Always use strong keys for encryption  

---

## 🌟 Future Improvements

- AES encryption support  
- Drag & drop interface  
- Cloud storage integration  
- Multi-image encoding  
- User authentication system  

---

## ⭐ Support

If you like this project:
- Star this repository  
- Fork it  
- Contribute improvements  

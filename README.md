📚 Library Management System
A fully-featured desktop Library Management System built with Python, Tkinter (ttkbootstrap), and SQLite3 as part of a Project-Based Learning (PBL) initiative.
The application follows a clean OOP architecture with a separated database layer (DatabaseManager) and UI layer (LibraryApp), and uses a normalized relational database schema with three tables — books, members, and transactions.
✨ Features

📊 Live Dashboard — 6 real-time stat cards (Total Books, Available, Issued, Overdue, Members, Total Fines)
📖 Book Management — Add books with Title, Author, Genre, ISBN, and multiple copies; delete with safety checks
👥 Member Management — Register members with name, email, and phone
📤 Issue & Return System — Issue books with configurable loan durations (7 / 14 / 30 / 60 days)
⚠️ Overdue Fine Calculation — Automatically calculates fines at ₹2/day on return
🔍 Live Search & Filter — Real-time search across Books, Members, and Transactions
🎨 Color-coded Status — Overdue (red), Active (orange), Returned (green)
📥 CSV Export — Export Books and Transactions to .csv
🔄 Auto Schema Migration — Safely upgrades older database versions on first run

🛠️ Tech Stack
Python 3.8+  |  Tkinter  |  ttkbootstrap  |  SQLite3  |  CSV

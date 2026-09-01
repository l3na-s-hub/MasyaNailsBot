"""Проверка Google Calendar. Запуск из папки бота:
   python test_calendar.py
"""
import logging
logging.basicConfig(level=logging.INFO)

from services.google_calendar import test_connection

print("=" * 50)
print(test_connection())
print("=" * 50)

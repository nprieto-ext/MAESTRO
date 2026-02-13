#!/usr/bin/env python3
"""Test minimal pour vérifier que paintEvent fonctionne"""

import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtCore import Qt, QRect

class TestTrack(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(800, 60)
        self.setStyleSheet("background: #0a0a0a;")
        
        # Données des clips
        self.clips = [
            {"x": 100, "width": 200, "color": QColor("#ff0000"), "intensity": 100},
            {"x": 350, "width": 150, "color": QColor("#00ff00"), "intensity": 75},
        ]
    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        print(f"🖼️ PAINT CALLED - Drawing {len(self.clips)} clips")
        
        # Dessiner les clips
        for i, clip in enumerate(self.clips):
            rect = QRect(clip["x"], 10, clip["width"], 40)
            
            # Fond couleur
            painter.fillRect(rect, clip["color"])
            
            # Bordure
            painter.setPen(QPen(QColor("#2a2a2a"), 2))
            painter.drawRoundedRect(rect, 6, 6)
            
            # Texte
            painter.setPen(QColor(255, 255, 255))
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(14)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, f"{clip['intensity']}%")
            
            print(f"   Clip {i}: x={clip['x']}, color={clip['color'].name()}")

class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Paint - Les couleurs DOIVENT apparaître")
        self.setFixedSize(820, 100)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        track = TestTrack()
        layout.addWidget(track)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    
    print("=" * 60)
    print("TEST PAINT - Si vous voyez 2 rectangles colorés (rouge et vert),")
    print("le dessin fonctionne et le problème est ailleurs.")
    print("Si vous ne voyez RIEN, le problème est dans Qt/Python.")
    print("=" * 60)
    
    sys.exit(app.exec())
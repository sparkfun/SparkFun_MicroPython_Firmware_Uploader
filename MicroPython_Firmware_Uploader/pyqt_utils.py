from PyQt5.QtWidgets import QDialog, QListWidget, QVBoxLayout, QPushButton, QListWidgetItem
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QListWidget, QVBoxLayout, QListWidgetItem, QWidget, QLabel, QHBoxLayout
from PyQt5.QtCore import Qt, QSize


class PopupListItemWidget(QWidget):
    def __init__(self, text, description=None, icon=None, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout()

        # Add icon if present
        if icon:
            icon_label = QLabel()
            icon_label.setPixmap(icon.pixmap(64, 64))
            icon_label.setFixedSize(80, 80)
            icon_label.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(icon_label, alignment=Qt.AlignVCenter)

        # Text and description
        text_layout = QVBoxLayout()

        text_label = QLabel(text)
        text_label.setStyleSheet("font-size: 14px; font-weight: bold; color: black; background: transparent; border: none")
        text_layout.addWidget(text_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet("color: #666666; font-size: 11px; background: transparent; border: none")
            desc_label.setWordWrap(True)
            text_layout.addWidget(desc_label)

        layout.addLayout(text_layout)
        self.setLayout(layout)

        # Only set border/background for the whole widget, not for inner widgets
        self.setStyleSheet("""
            background-color: #FFFFFF;
        """)

class PopupWindow(QDialog):
    def __init__(self, items=None, title="Pop-up Window", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.list_widget = QListWidget(self)
        self.list_widget.setFocusPolicy(Qt.NoFocus)
        self.list_widget.setIconSize(QSize(64, 64))
        self._item_text_map = {}  # Maps item text to QListWidgetItem

        if items:
            for item in items:
                # If item is a QListWidgetItem, try to get description from its data
                text = item.text() if isinstance(item, QListWidgetItem) else str(item)
                icon = item.icon() if isinstance(item, QListWidgetItem) else None
                description = item.data(Qt.UserRole) if isinstance(item, QListWidgetItem) else ""
                widget = PopupListItemWidget(text, description, icon)
                list_item = QListWidgetItem()
                list_item.setSizeHint(widget.sizeHint())
                self.list_widget.addItem(list_item)
                self.list_widget.setItemWidget(list_item, widget)
                self._item_text_map[text] = list_item

        self.list_widget.itemClicked.connect(self.item_selected)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.list_widget)
        self.setLayout(layout)
        self.parent = parent

    def item_selected(self, item):
        if self.parent:
            # Find the text for the clicked item by comparing with the map
            text = None
            for t, list_item in self._item_text_map.items():
                if list_item is item:
                    text = t
                    break
            if text is None:
                text = item.text()
            self.parent.setText(text)
            self.accept()

class PopupListButton(QPushButton):
    textChanged = pyqtSignal(str)

    def __init__(self, text, items=None, title="Pop-up Window", parent=None, popUpCallbacks=None, addTooltip=False):
        super().__init__(text, parent)
        self.items = items or []  # Default to an empty list if no items are provided
        self.popUpTitle = title
        self.clicked.connect(self.open_popup)
        self.popup = None
        self.popUpCallbacks = popUpCallbacks  # Callbacks to run before opening the popup
        self.addTooltip = addTooltip  # Flag to determine if we should add a tooltip
        self.storedDataDict = {}  # Dictionary to store data for each item. Maps item text to stored data of any type

    def open_popup(self):
        for callback in self.popUpCallbacks or []:
            callback()

        # Recreate the popup window with the current items to ensure they are visible
        if self.items is not None:
            try:
                items_to_show = [item.clone() for item in self.items]  # Clone items to avoid modifying the original list (was necessary)
            except AttributeError: # For when strings are passed in instead of QListWidgetItems
                items_to_show = self.items
        
        self.popup = PopupWindow(items_to_show, self.popUpTitle, self)
        self.popup.resize(600, 400)  # Set a larger size for the popup window
        self.popup.show()

    def addIconItem(self, text: str, description: str, iconPath: str, storedData=None) -> None:
        """Add an item with a description and an icon to the popup items."""
        icon = QIcon(iconPath)
        item = QListWidgetItem(icon, text)
        item.setData(Qt.UserRole, description)  # Store the description for use in PopupListItemWidget
        item.setSizeHint(QSize(400, 100))
        self.items.append(item)  # Add the item to the list of items
        if storedData is not None:
            self.storedDataDict[text] = storedData
    
    def setText(self, text: str) -> None:
        """Set the text of the button."""
        super().setText(text)  # Call the parent class's setText method
        if self.addTooltip:
            self.setToolTip(text) # Set the tooltip to mirror the text (helps for long text)
        self.textChanged.emit(text)  # Emit the textChanged signal

    def getStoredData(self, text: str) -> str:
        """Get the stored data for the item with the given text."""
        return self.storedDataDict.get(text, None)
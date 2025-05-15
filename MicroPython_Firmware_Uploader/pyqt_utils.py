from PyQt5.QtWidgets import QDialog, QListWidget, QVBoxLayout, QPushButton, QListWidgetItem
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QIcon

class PopupWindow(QDialog):
    def __init__(self, items=None, title="Pop-up Window", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove the "help" button
        self.list_widget = QListWidget(self)
        self.list_widget.setFocusPolicy(Qt.NoFocus)  # Disable focus on the list widget
        self.list_widget.setIconSize(QSize(64, 64))  # Set icon size for the list items

        if items:
            for item in items:
                self.list_widget.addItem(item)  # Add each item to the list widget

        self.list_widget.itemClicked.connect(self.item_selected)  # Connect item click signal to handler
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        layout.addWidget(self.list_widget)
        self.setLayout(layout)
        self.parent = parent

    def item_selected(self, item):
        if self.parent:  # Check if parent exists
            self.parent.setText(item.text())  # Change button text to selected item's text
            self.accept()  # Close the popup window properly

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
        # item.setToolTip(description)  # Set the tooltip to show the description
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
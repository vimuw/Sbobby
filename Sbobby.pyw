"""
Entrypoint leggero (compatibile con PyInstaller).

La logica dell'app vive in `sbobby/app.py` per mantenere il progetto modulare.
"""

from sbobby.app import SbobbyApp


def main() -> None:
    app = SbobbyApp()
    app.mainloop()


if __name__ == "__main__":
    main()


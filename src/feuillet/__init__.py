__version__ = "0.1.0"

# Limites anti-« bombe de décompression » appliquées dès l'import du paquet.
from feuillet.core import limits as _limits  # noqa: F401 - import pour son effet (limites)

from .models import Base

# Import all models so that alembic can detect them from the Base class's
# metadata
from chat import models as chat_models
from emails import models as email_models
from profiles import models as profile_models

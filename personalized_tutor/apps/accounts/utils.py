from django.contrib.auth import get_user_model

GUEST_USER_EMAIL = "guest@localhost"


def get_guest_user():
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        email=GUEST_USER_EMAIL,
        defaults={"username": "guest"},
    )
    return user


def get_agent_user(request):
    if hasattr(request, "user") and request.user.is_authenticated:
        return request.user
    return get_guest_user()


def ensure_learner_profile(user):
    from apps.accounts.models import LearnerProfile

    profile, _ = LearnerProfile.objects.get_or_create(user=user)
    return profile

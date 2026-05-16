"""
SM-2 Spaced Repetition implementation.

Reference: https://www.supermemo.com/en/blog/application-of-a-computer-to-improve-the-results-obtained-in-working-with-the-supermemo-method

Quality scale (0–5):
  5 - perfect response
  4 - correct after a hesitation
  3 - correct with serious difficulty
  2 - incorrect; correct answer seemed easy to recall
  1 - incorrect; correct answer was hard to recall
  0 - complete blackout
"""

from datetime import date, timedelta
import math


def sm2_update(easiness: float, interval: int, repetitions: int, quality: int) -> tuple:
    """
    Run one SM-2 iteration.

    Returns:
        (new_easiness, new_interval, new_repetitions)
    """
    if quality < 3:
        # Failed — reset
        new_reps = 0
        new_interval = 1
    else:
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = math.ceil(interval * easiness)
        new_reps = repetitions + 1

    # Update easiness factor
    new_easiness = easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_easiness = max(1.3, new_easiness)

    return round(new_easiness, 3), new_interval, new_reps


def next_review_date(interval: int) -> date:
    return date.today() + timedelta(days=interval)


def get_due_cards(user):
    """Return all review cards due today or earlier."""
    from apps.learning.models import ReviewCard
    return ReviewCard.objects.filter(user=user, next_review__lte=date.today()).select_related("topic")


def record_review(card, quality: int):
    """Apply SM-2 to a card and save."""
    new_e, new_i, new_r = sm2_update(card.easiness, card.interval, card.repetitions, quality)
    card.easiness = new_e
    card.interval = new_i
    card.repetitions = new_r
    card.last_quality = quality
    card.next_review = next_review_date(new_i)
    card.save()

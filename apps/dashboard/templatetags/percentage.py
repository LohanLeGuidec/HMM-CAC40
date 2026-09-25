from django import template

register = template.Library()


@register.filter
def percentage(value):
    """Convertit une proportion décimale en pourcentage affichable."""
    if value is None:
        return None
    return float(value) * 100

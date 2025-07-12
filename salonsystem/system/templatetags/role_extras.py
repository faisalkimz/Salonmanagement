from django import template

register = template.Library()

@register.filter
def has_feature(role, feature_code):
    if not role:
        return False
    return role.features.filter(code=feature_code).exists()
"""Effective entitlements, kept separate from saved company preferences.

Preferences and historical evidence survive downgrades. They only become active
again when the current subscription includes the corresponding feature.
"""
from .plans import get_plan_limits, is_plan_active


def feature_enabled(user, feature):
    return bool(user and is_plan_active(user) and
                get_plan_limits(user.plan or 'starter').get(feature, False))


def delivery_preferences(user):
    limits = get_plan_limits(user.plan or 'starter') if user else {}
    features = {key: feature_enabled(user, key) for key in limits if key.startswith('has_')}
    return {
        'delivery_signature_enabled': bool(features.get('has_delivery_signature') and
                                           getattr(user, 'delivery_signature_enabled', False)),
        'delivery_photo_required': bool(features.get('has_photo_proof') and
                                       getattr(user, 'needs_photo_proof', False)),
        'features': features,
    }

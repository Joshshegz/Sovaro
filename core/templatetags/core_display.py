from django import template


register = template.Library()


@register.filter
def content_label(value):
    """Turn stored strategy keys into readable labels without changing the data."""
    labels = {
        "educational_informational": "Teaching",
        "entertainment_humour": "Entertainment",
        "community_interactive": "Community",
        "product_service_education": "Product or service",
        "customer_proof_stories": "Customer stories",
        "proof_and_process": "Proof and process",
    }
    key = str(value or "").lower()
    return labels.get(key, key.replace("_", " ").capitalize())

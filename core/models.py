from django.db import models


class PlatformChoices(models.TextChoices):
    LINKEDIN = 'linkedin', 'LinkedIn'
    INSTAGRAM = 'instagram', 'Instagram'
    TIKTOK = 'tiktok', 'TikTok'


class BrandProfile(models.Model):
    """Stores business context and positioning for content generation."""
    name = models.CharField(max_length=255)
    niche = models.CharField(max_length=255, help_text="e.g. B2B SaaS, Health & Fitness")
    target_audience = models.TextField(help_text="Detailed description of the ideal customer")
    tone_of_voice = models.CharField(
        max_length=255,
        default="Engaging, authoritative, approachable",
        help_text="e.g. Direct, conversational, witty, professional"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Competitor(models.Model):
    """Competitors or inspiration accounts monitored by a brand."""
    brand = models.ForeignKey(BrandProfile, on_delete=models.CASCADE, related_name='competitors')
    platform = models.CharField(max_length=20, choices=PlatformChoices.choices)
    handle = models.CharField(max_length=255, help_text="e.g. @acme or linkedin.com/in/acme")
    profile_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.handle} ({self.platform})"


class SocialPost(models.Model):
    """
    Holds posts collected from competitors or manually pasted by the user.
    Includes viral outlier metrics.
    """
    brand = models.ForeignKey(BrandProfile, on_delete=models.CASCADE, related_name='posts')
    competitor = models.ForeignKey(
        Competitor, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts'
    )
    platform = models.CharField(max_length=20, choices=PlatformChoices.choices)
    post_url = models.URLField(blank=True, null=True)

    # Content fields
    hook_text = models.TextField(help_text="The first 2-3 lines or main hook of the post/video")
    full_content = models.TextField(blank=True, null=True, help_text="Full caption or transcript")

    # Metrics
    views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    comments = models.PositiveIntegerField(default=0)

    # Intelligence / Outlier analysis
    outlier_score = models.FloatField(default=1.0, help_text="Multiplication factor vs median (e.g. 3.2x)")
    is_outlier = models.BooleanField(default=False, help_text="True if outlier_score >= 2.5")
    is_manual = models.BooleanField(default=True, help_text="True if entered manually by user")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.platform}] {self.hook_text[:40]}..."


class GeneratedIdea(models.Model):
    """AI-generated content concepts adapted specifically for the brand."""
    brand = models.ForeignKey(BrandProfile, on_delete=models.CASCADE, related_name='ideas')
    source_post = models.ForeignKey(
        SocialPost, on_delete=models.SET_NULL, null=True, blank=True, related_name='generated_ideas'
    )
    target_platform = models.CharField(max_length=20, choices=PlatformChoices.choices)
    title = models.CharField(max_length=255)
    hook = models.TextField(help_text="Suggested hook line")
    body_content = models.TextField(help_text="Full script, carousel breakdown, or post body")
    why_it_works = models.TextField(blank=True, null=True, help_text="AI rationale for the viral hook")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.target_platform}] {self.title}"

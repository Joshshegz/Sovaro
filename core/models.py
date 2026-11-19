from django.conf import settings
from django.db import models


class PlatformChoices(models.TextChoices):
    LINKEDIN = 'linkedin', 'LinkedIn'
    INSTAGRAM = 'instagram', 'Instagram'
    TIKTOK = 'tiktok', 'TikTok'
    TWITTER = 'twitter', 'X (Twitter)'
    YOUTUBE = 'youtube', 'YouTube'
    ALL_SOCIALS = 'all_socials', 'All Socials'


class BrandProfile(models.Model):
    """Stores business context and positioning for content generation."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='brands',
        null=True,
        blank=True,
        help_text="The user/tenant who owns this brand"
    )
    name = models.CharField(max_length=255)
    brand_image = models.ImageField(
        upload_to="brand_images/%Y/%m/",
        blank=True,
        null=True,
        help_text="Brand logo or profile image",
    )
    niche = models.CharField(max_length=255, help_text="e.g. B2B SaaS, Health & Fitness")
    business_model = models.CharField(
        max_length=100,
        default="b2b_saas",
        blank=True,
        help_text="e.g. b2b_saas, d2c_ecommerce, professional_services, local_business"
    )
    primary_goal = models.CharField(
        max_length=255,
        default="Direct Sales & Lead Generation",
        blank=True,
        help_text="e.g. Lead Generation, Brand Awareness, Sales"
    )
    weekly_posts_capacity = models.PositiveIntegerField(
        default=3,
        help_text="Realistic number of social posts the brand can publish each week"
    )
    conversion_url = models.URLField(
        blank=True,
        null=True,
        help_text="Primary destination link for calls to action"
    )
    target_audience = models.TextField(help_text="Detailed description of the ideal customer")
    tone_of_voice = models.CharField(
        max_length=255,
        default="Engaging, authoritative, approachable",
        help_text="e.g. Direct, conversational, witty, professional"
    )
    negative_guardrails = models.TextField(
        blank=True,
        default="",
        help_text="Claims, promises, or topics the brand will never make"
    )
    brand_values = models.JSONField(default=list, blank=True)
    content_themes = models.JSONField(default=list, blank=True)
    content_formats = models.JSONField(
        default=list,
        blank=True,
        help_text="Production capabilities: talking_head, b_roll, screen_demo, carousels, text_threads"
    )
    social_profiles = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detected or specified brand social profiles e.g. {'linkedin': '...', 'twitter': '...', 'youtube': '...'}"
    )
    social_assessment = models.JSONField(
        default=dict,
        blank=True,
        help_text="Social footprint analysis: recommended primary & secondary channels, presence summary"
    )
    strategy_inputs = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class BrandMemory(models.Model):
    CATEGORY_CHOICES = (
        ("brand_fact", "Brand fact"),
        ("offer", "Offer or product"),
        ("audience_insight", "Audience insight"),
        ("customer_language", "Customer language"),
        ("performance_lesson", "Performance lesson"),
        ("guardrail", "Claim or topic to avoid"),
    )
    STATUS_CHOICES = (
        ("confirmed", "Confirmed"),
        ("hypothesis", "Working hypothesis"),
        ("needs_confirmation", "Needs confirmation"),
    )

    brand = models.ForeignKey(BrandProfile, on_delete=models.CASCADE, related_name="memories")
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES)
    statement = models.TextField()
    evidence = models.TextField(blank=True, default="")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="needs_confirmation")
    source = models.CharField(max_length=30, default="user", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "-updated_at"]

    def __str__(self):
        return f"{self.brand.name}: {self.statement[:60]}"


class Competitor(models.Model):
    """Competitors or inspiration accounts monitored by a brand across socials."""
    brand = models.ForeignKey(BrandProfile, on_delete=models.CASCADE, related_name='competitors')
    name = models.CharField(max_length=255, blank=True, default='', help_text="Company or Creator Name (e.g. Acme Corp)")
    platform = models.CharField(max_length=20, choices=PlatformChoices.choices, default=PlatformChoices.ALL_SOCIALS)
    handle = models.CharField(max_length=255, help_text="Primary handle e.g. @acme or linkedin.com/in/acme")
    profile_url = models.URLField(blank=True, null=True, help_text="Primary website or profile link")

    # Social handles across all networks
    social_handles = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dictionary of handles across networks: {'linkedin': '...', 'instagram': '...', 'tiktok': '...', 'twitter': '...', 'youtube': '...'}"
    )

    # Core Competitor Social Intelligence: What they do & What works for them
    what_they_do = models.TextField(blank=True, default="", help_text="Summary of themes, content formats, tone, and tactics across socials")
    what_works = models.TextField(blank=True, default="", help_text="What performs best: highest-engagement topics, winning formats, key triggers")
    top_hooks = models.JSONField(default=list, blank=True, help_text="List of high-performing hook patterns or opening lines they use")
    content_formats = models.JSONField(default=list, blank=True, help_text="Winning formats: e.g. Carousels, Short-form teardowns, Text threads, Demos")
    differentiation_opportunities = models.TextField(blank=True, default="", help_text="White space opportunities and ways our brand can out-execute them")

    # Full structured AI analysis payload & metadata
    analysis_data = models.JSONField(default=dict, blank=True, help_text="Full structured JSON payload from Gemini")
    last_analyzed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        display_name = self.name or self.handle
        return f"{display_name} ({self.platform})"


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


class MonthlyReport(models.Model):
    """
    Stores executive monthly client reports generated by the reporting engine.
    Persists validated metrics, scorecards, post analytics, and structured strategic deliverables.
    """
    brand = models.ForeignKey(BrandProfile, on_delete=models.CASCADE, related_name='reports')
    month_year = models.CharField(max_length=100, help_text="e.g. October 1–31, 2026 or October 2026")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    platforms_covered = models.JSONField(default=list, blank=True)

    # Raw and validated metric data
    raw_metrics = models.JSONField(default=dict, blank=True, help_text="Raw or normalized current period metrics")
    previous_period_metrics = models.JSONField(default=dict, blank=True, help_text="Metrics from previous period for comparison")
    scorecard_data = models.JSONField(default=dict, blank=True, help_text="Deterministic scorecard calculations (abs and % changes)")
    post_records = models.JSONField(default=list, blank=True, help_text="Post-level analytics rows imported or entered")
    content_performance = models.JSONField(default=dict, blank=True, help_text="Top and low post insights")

    # Strategic deliverables (editable by user)
    executive_summary = models.TextField(blank=True, default="", help_text="Executive narrative summary")
    what_worked = models.TextField(blank=True, default="", help_text="Reviewed observations and hypotheses")
    competitor_snapshot = models.TextField(blank=True, default="", help_text="User supplied competitor observations")
    next_month_plan = models.TextField(blank=True, default="", help_text="Reviewed themes and actions for next month")
    status = models.CharField(max_length=12, default="draft", choices=(("draft", "Draft"), ("ready", "Ready to share")))
    key_insights = models.JSONField(default=list, blank=True, help_text="Key analytical insights")
    strategic_insights = models.JSONField(default=list, blank=True, help_text="Structured observations, hypotheses, and recommendations")
    objective_assessment = models.JSONField(default=list, blank=True, help_text="Evaluation against brand goals and targets")
    next_month_recommendations = models.JSONField(default=list, blank=True, help_text="Prioritized next-month action items")
    next_month_strategy = models.JSONField(default=dict, blank=True, help_text="Legacy format (double_down, test, stop)")

    data_provenance = models.CharField(max_length=50, default="manual_entry", blank=True, help_text="e.g. manual_entry, csv_import")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Report for {self.brand.name} - {self.month_year}"


class ContentStrategy(models.Model):
    """
    PILLAR 3: CONTENT STRATEGY
    A full AI-generated content strategy for a brand, covering:
    - Content pillars, platform playbook, content mix, posting schedule,
      30 content ideas, KPIs, and CTA strategy.
    Generated once per brand and can be regenerated anytime.
    """
    brand = models.ForeignKey(BrandProfile, on_delete=models.CASCADE, related_name='strategies')
    strategy_foundation = models.JSONField(default=dict, blank=True)

    # Strategic presentation & ICP fields
    executive_summary = models.TextField(
        blank=True,
        default="",
        help_text="2-3 sentence strategic rationale and core positioning idea"
    )
    audience_icp_dossier = models.JSONField(
        default=dict,
        blank=True,
        help_text="Friction, status desire, category enemy, and buying objections"
    )

    # AI-generated strategy sections — all stored as JSON for flexibility
    content_pillars = models.JSONField(
        help_text="List of 4-5 core content themes with descriptions and example topics"
    )
    platform_playbook = models.JSONField(
        help_text="Per-platform recommendations: priority, rationale, content types"
    )
    content_mix = models.JSONField(
        help_text="Percentage breakdown: educational, entertaining, promotional, personal"
    )
    posting_schedule = models.JSONField(
        help_text="Recommended posting frequency per platform"
    )
    content_ideas = models.JSONField(
        help_text="30 ready-to-use content ideas mapped to pillars and platforms"
    )
    kpis = models.JSONField(
        help_text="Key performance indicators to track success by platform"
    )
    cta_strategy = models.JSONField(
        help_text="Call-to-action recommendations by awareness stage"
    )
    content_gap_research = models.JSONField(
        default=dict,
        blank=True,
        help_text="Grounded competitor coverage, whitespace findings, sources and research queries",
    )
    content_gap_researched_at = models.DateTimeField(null=True, blank=True)
    weekly_plan = models.JSONField(
        default=list,
        blank=True,
        help_text="Executable first-week posts with platform, format, hook, CTA, owner and status",
    )
    validation_report = models.JSONField(
        default=dict,
        blank=True,
        help_text="Deterministic quality-gate results recorded when the strategy was created",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Strategy for {self.brand.name} ({self.created_at.strftime('%b %Y')})"


class PostResult(models.Model):
    ACTION_CHOICES = (
        ("repeat", "Repeat"),
        ("change", "Change"),
        ("stop", "Stop"),
        ("test", "Test next"),
        ("insufficient", "Not enough evidence"),
    )

    brand = models.ForeignKey(BrandProfile, on_delete=models.CASCADE, related_name="post_results")
    strategy = models.ForeignKey(ContentStrategy, on_delete=models.SET_NULL, null=True, blank=True, related_name="post_results")
    plan_key = models.CharField(max_length=80, blank=True, default="")
    title = models.CharField(max_length=255)
    platform = models.CharField(max_length=40, blank=True, default="")
    published_on = models.DateField(null=True, blank=True)
    reach = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)
    saves = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    comments = models.PositiveIntegerField(default=0)
    link_clicks = models.PositiveIntegerField(default=0)
    enquiries = models.PositiveIntegerField(default=0)
    sales = models.PositiveIntegerField(default=0)
    observation = models.TextField(blank=True, default="")
    lesson = models.TextField(blank=True, default="")
    next_action = models.CharField(max_length=20, choices=ACTION_CHOICES, default="insufficient")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_on", "-created_at"]

    def __str__(self):
        return f"{self.brand.name}: {self.title}"


class RepurposeProject(models.Model):
    MODE_CHOICES = (("repurpose", "Repurpose existing content"), ("fresh", "Start from a rough idea"))
    brand = models.ForeignKey(BrandProfile, on_delete=models.CASCADE, related_name="repurpose_projects")
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    source_title = models.CharField(max_length=255, blank=True, default="")
    source_content = models.TextField()
    platforms = models.JSONField(default=list)
    objective = models.CharField(max_length=30)
    desired_action = models.CharField(max_length=255, blank=True, default="")
    source_analysis = models.JSONField(default=dict, blank=True)
    hook_options = models.JSONField(default=list, blank=True)
    outputs = models.JSONField(default=list, blank=True)
    quality_report = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.source_title or f"Repurpose project {self.pk}"

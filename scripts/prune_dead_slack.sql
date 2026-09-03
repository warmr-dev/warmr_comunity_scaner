-- Prune dead/system Slack hosts + join_url duplicates from community_scanner.
-- Preview counts first, then DELETE.

-- 1) Slack product/marketing hosts (not communities)
SELECT COUNT(*) AS slack_system_drop
FROM community_scanner
WHERE platform = 'slack'
  AND lower(coalesce(platform_id, '')) IN (
    'app','api','status','slack','www','get','help','join','dev','developer','developers',
    'files','edge','hooks','corp','enterprise','admin','signin','login','docs','support',
    'blog','store','download','downloads','mobile','desktop','sales','partners','security',
    'legal','privacy','careers','about','cdn','auth','sso','billing','marketplace','apps',
    'bot','bots','connect','demo','sandbox','example','sample','test','staging','community',
    'communities','workspace-signin','solutions','resources','intl','ssb','go','my','a','b',
    'mail','email','feedback','brand','newsroom','trust','slackb','slackhq','slack-marketing',
    'slack-sales-and-cs','xyz','null','undefined'
  );

-- 2) Duplicate join_url: keep platform:* key, drop site:*
WITH ranked AS (
  SELECT id, canonical_key, join_url,
         ROW_NUMBER() OVER (
           PARTITION BY lower(regexp_replace(join_url, '/$', ''))
           ORDER BY
             CASE WHEN canonical_key LIKE 'site:%' THEN 1 ELSE 0 END,
             last_seen_at DESC NULLS LAST,
             first_seen_at DESC NULLS LAST
         ) AS rn
  FROM community_scanner
  WHERE join_url IS NOT NULL AND join_url <> ''
)
SELECT COUNT(*) AS join_url_dupe_drop FROM ranked WHERE rn > 1;

-- DELETE slack system hosts
DELETE FROM community_scanner
WHERE platform = 'slack'
  AND lower(coalesce(platform_id, '')) IN (
    'app','api','status','slack','www','get','help','join','dev','developer','developers',
    'files','edge','hooks','corp','enterprise','admin','signin','login','docs','support',
    'blog','store','download','downloads','mobile','desktop','sales','partners','security',
    'legal','privacy','careers','about','cdn','auth','sso','billing','marketplace','apps',
    'bot','bots','connect','demo','sandbox','example','sample','test','staging','community',
    'communities','workspace-signin','solutions','resources','intl','ssb','go','my','a','b',
    'mail','email','feedback','brand','newsroom','trust','slackb','slackhq','slack-marketing',
    'slack-sales-and-cs','xyz','null','undefined'
  );

-- DELETE duplicate join_url rows (keep best)
WITH ranked AS (
  SELECT id,
         ROW_NUMBER() OVER (
           PARTITION BY lower(regexp_replace(join_url, '/$', ''))
           ORDER BY
             CASE WHEN canonical_key LIKE 'site:%' THEN 1 ELSE 0 END,
             last_seen_at DESC NULLS LAST,
             first_seen_at DESC NULLS LAST
         ) AS rn
  FROM community_scanner
  WHERE join_url IS NOT NULL AND join_url <> ''
)
DELETE FROM community_scanner
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

-- Soft prune for community_scanner (preview first, then delete).
-- Soft keep ≈ invite-shaped, not Russian-flagged, not obvious listicle junk.

-- 1) Preview drops
SELECT COUNT(*) AS would_drop
FROM community_scanner
WHERE
  COALESCE(raw_signals->>'maybe_russian','') = 'true'
  OR name ~* '(discord servers|all discord|list of|how to create|review –|http://|https://)'
  OR platform_id IN ('username','share','joinchat','invite')
  OR platform NOT IN ('telegram','discord','whatsapp','slack')
  OR (size_members IS NOT NULL AND (size_members < 50 OR size_members > 500000));

-- 2) Delete junk (run only when ready)
-- DELETE FROM community_scanner
-- WHERE
--   COALESCE(raw_signals->>'maybe_russian','') = 'true'
--   OR name ~* '(discord servers|all discord|list of|how to create|review –|http://|https://)'
--   OR platform_id IN ('username','share','joinchat','invite')
--   OR platform NOT IN ('telegram','discord','whatsapp','slack')
--   OR (size_members IS NOT NULL AND (size_members < 50 OR size_members > 500000));

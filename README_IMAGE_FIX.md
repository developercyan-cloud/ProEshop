# ProEshop image and Rolex catalog repair

## Changes
- Keeps the existing app structure, tabs, cart, orders, and account views.
- Temporarily hides Amazon, Target, and Walmart; the API also rejects searches and cart additions for those stores.
- Keeps Rolex, HUBLOT, and Jewelers Toy Store as the visible store options.
- Keeps 47 Rolex references, applies the ProEshop 50% calculation to all 47, and returns original/list and discounted prices. The discount is a ProEshop simulation, not an official Rolex promotion.
- Adds local bundled image fallbacks for every HUBLOT and Rolex catalog item and all four Jewelers Toy Store products. Official Rolex/HUBLOT image URLs are used first where available; if the remote CDN fails, the UI swaps to a local fallback.
- Stops server-side scraping of Hublot/Jewelers product pages during each search, which was producing HTTP 403 errors.
- Cart and checkout save local image paths so the images remain visible.

## Important image note
The local fallback images are illustrative crops from the generated catalog sheets, and the Jewelers fallback images are illustrative product renders. They are not represented as official manufacturer photography. The app prefers official Rolex/HUBLOT image URLs where configured.

## Railway deployment
Upload this ZIP as the project source and deploy. Keep `DATABASE_PATH=/data/shopcart.db` and the existing persistent volume unchanged; do not delete or recreate the database/volume.

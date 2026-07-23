// Integration providers the Brand Library can connect. Field keys map to the
// backend connect body: "config.*" -> config object, "credentials.*" -> creds.

export const PROVIDERS = {
  shopify: {
    name: 'Shopify Store', color: '#95bf47', letter: 'S',
    help: 'Dev Dashboard app credentials, or a legacy access token.',
    fields: [
      { k: 'config.shop_domain', label: 'Shop domain (store.myshopify.com)' },
      { k: 'credentials.client_id', label: 'API key / Client ID' },
      { k: 'credentials.client_secret', label: 'API secret', secret: true },
    ],
  },
  meta_ads: {
    name: 'Meta Ads', color: '#1877f2', letter: 'f',
    help: 'Ad account id + a Marketing API access token.',
    fields: [
      { k: 'config.ad_account_id', label: 'Ad account ID (act_...)' },
      { k: 'credentials.access_token', label: 'Access token', secret: true },
    ],
  },
  ga4: {
    name: 'Google Analytics 4', color: '#e8710a', letter: 'G',
    help: 'GA4 property id + an access token.',
    fields: [
      { k: 'config.property_id', label: 'Property ID' },
      { k: 'credentials.access_token', label: 'Access token', secret: true },
    ],
  },
  clarity: {
    name: 'Microsoft Clarity', color: '#4a4af0', letter: 'C',
    help: 'Data Export API token (Settings -> Data Export).',
    fields: [
      { k: 'credentials.token', label: 'Data Export API token', secret: true },
    ],
  },
}

export const COMING = {
  google_ads: { name: 'Google Ads', color: '#4285f4', letter: 'G' },
  search_console: { name: 'Search Console', color: '#458cf5', letter: 'S' },
}

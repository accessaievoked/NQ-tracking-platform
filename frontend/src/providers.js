// Integration providers the Brand Library can connect. Field keys map to the
// backend connect body: "config.*" -> config object, "credentials.*" -> creds.
//
// Field flags: `secret` masks the input, `multiline` renders a textarea (for
// pasted JSON keys), `optional` greys the label and adds a hint line.

export const PROVIDERS = {
  shopify: {
    name: 'Shopify Store', color: '#95bf47', letter: 'S',
    oauth: true,
    help: 'Enter your store domain and approve access on Shopify — no keys to paste.',
    fields: [
      { k: 'config.shop_domain', label: 'Shop domain (store.myshopify.com)' },
    ],
  },
  meta_ads: {
    name: 'Meta Ads', color: '#1877f2', letter: 'f',
    help: 'Ad account id + the extended access token from the Access Token Debugger. '
        + 'Add the app id and secret too — they are what lets the backend renew the '
        + 'token before it expires, so the connection does not go dark after 60 days.',
    fields: [
      { k: 'config.ad_account_id', label: 'Ad account ID (act_...)' },
      { k: 'credentials.access_token', label: 'Access token (extended)', secret: true },
      { k: 'credentials.app_id', label: 'App ID' },
      { k: 'credentials.app_secret', label: 'App secret', secret: true },
    ],
  },
  google_ads: {
    name: 'Google Ads', color: '#4285f4', letter: 'G',
    help: 'Customer id + the manager account’s developer token + an OAuth client and '
        + 'refresh token for the adwords scope. The backend refreshes access tokens '
        + 'on its own — nothing to re-paste.',
    fields: [
      { k: 'config.customer_id', label: 'Customer ID (10 digits)' },
      { k: 'credentials.developer_token', label: 'Developer token', secret: true },
      { k: 'credentials.client_id', label: 'OAuth client ID' },
      { k: 'credentials.client_secret', label: 'OAuth client secret', secret: true },
      { k: 'credentials.refresh_token', label: 'Refresh token', secret: true },
      {
        k: 'config.login_customer_id', label: 'Manager (MCC) ID', optional: true,
        hint: 'Only when the account is managed by an MCC.',
      },
    ],
  },
  ga4: {
    name: 'Google Analytics 4', color: '#e8710a', letter: 'G',
    help: 'Property id + the service account JSON key, with that service account '
        + 'granted Viewer on the property. This connects permanently — the backend '
        + 'mints its own tokens, nothing to re-paste.',
    fields: [
      { k: 'config.property_id', label: 'Property ID (9 digits)' },
      {
        k: 'credentials.service_account', label: 'Service account JSON key',
        secret: true, multiline: true,
        hint: 'Paste the whole downloaded .json file.',
      },
      {
        k: 'credentials.client_id', label: 'OAuth client ID', optional: true,
        hint: 'Only if connecting with an OAuth refresh token instead of a key.',
      },
      { k: 'credentials.client_secret', label: 'OAuth client secret', secret: true, optional: true },
      { k: 'credentials.refresh_token', label: 'Refresh token', secret: true, optional: true },
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
  search_console: { name: 'Search Console', color: '#458cf5', letter: 'S' },
}

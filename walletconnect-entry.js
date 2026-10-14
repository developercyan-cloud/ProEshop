import { EthereumProvider } from '@walletconnect/ethereum-provider';

// Export a local browser global. The Mini App does not fetch ESM modules from a CDN.
window.ProEshopEthereumProvider = EthereumProvider;

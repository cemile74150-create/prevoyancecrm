// craco.config.js
const path = require("path");
require("dotenv").config();
process.env.TSC_COMPILE_ON_ERROR = "true";

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

function makeDevServerV5Compatible(devServerConfig) {
  const {
    https,
    onAfterSetupMiddleware,
    onBeforeSetupMiddleware,
    onListening,
    setupMiddlewares,
    ...compatibleConfig
  } = devServerConfig;

  compatibleConfig.server =
    typeof https === "object"
      ? { type: "https", options: https }
      : https
        ? "https"
        : "http";
  compatibleConfig.headers = {
    ...compatibleConfig.headers,
    "Cross-Origin-Resource-Policy": "same-origin",
  };

  if (onBeforeSetupMiddleware || setupMiddlewares) {
    compatibleConfig.setupMiddlewares = (middlewares, devServer) => {
      if (onBeforeSetupMiddleware) {
        onBeforeSetupMiddleware(devServer);
      }

      return setupMiddlewares
        ? setupMiddlewares(middlewares, devServer)
        : middlewares;
    };
  }

  compatibleConfig.onListening = (devServer) => {
    devServer.close ??= (callback) => devServer.stopCallback(callback);

    if (onListening) {
      onListening(devServer);
    }
    if (onAfterSetupMiddleware) {
      onAfterSetupMiddleware(devServer);
    }
  };

  return compatibleConfig;
}

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {
      const moteurAvs = path.resolve(
        __dirname,
        "../backend/analyse_prevoyance_engine/rules",
      );
      const appSrc = path.resolve(__dirname, "src");
      const allowedAvs = [
        path.join(moteurAvs, "comparatif-avs.ts"),
        path.join(moteurAvs, "avs-age.ts"),
      ];
      webpackConfig.resolve.plugins = (webpackConfig.resolve.plugins || []).filter(
        (plugin) => plugin.constructor.name !== "ModuleScopePlugin",
      );
      // Le module partagé est hors de src. Babel y injecte des helpers
      // @babel/runtime par chemin absolu : le plugin CRA les refuse.
      webpackConfig.resolve.plugins.push({
        apply(resolver) {
          resolver.hooks.file.tapAsync(
            "LeoSoftModuleScopePlugin",
            (request, _contextResolver, callback) => {
              if (!request.context || !request.context.issuer) return callback();
              const raw = String(request.__innerRequest_request || "");
              const root = String(request.descriptionFileRoot || "");
              const resolved = String(request.path || "");
              const inNodeModules = [raw, root, resolved].some(
                (value) =>
                  value.includes(`${path.sep}node_modules${path.sep}`) ||
                  value.includes("/node_modules/") ||
                  value.includes("\\node_modules\\"),
              );
              if (inNodeModules || !raw) return callback();
              const issuerOutside = path.relative(appSrc, request.context.issuer).startsWith("..");
              if (issuerOutside) return callback();
              const requestFullPath = path.resolve(path.dirname(request.context.issuer), raw);
              if (
                allowedAvs.includes(requestFullPath) ||
                requestFullPath.startsWith(moteurAvs)
              ) {
                return callback();
              }
              if (path.relative(appSrc, requestFullPath).startsWith("..")) {
                return callback(
                  new Error(
                    `You attempted to import ${raw} which falls outside of the project src/ directory. Relative imports outside of src/ are not supported.`,
                  ),
                );
              }
              return callback();
            },
          );
        },
      });
      const oneOf = (webpackConfig.module.rules || []).find((rule) =>
        Array.isArray(rule.oneOf),
      );
      if (oneOf) {
        for (const rule of oneOf.oneOf) {
          const loader = String(rule.loader || "");
          if (!loader.includes("babel-loader") || !rule.include) continue;
          const include = Array.isArray(rule.include) ? rule.include : [rule.include];
          const couvreSrc = include.some((item) => String(item).includes(`${path.sep}src`));
          if (couvreSrc) rule.include = include.concat(moteurAvs);
        }
      }

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }
      return webpackConfig;
    },
  },
};

webpackConfig.devServer = (devServerConfig) => {
  // Add health check endpoints if enabled
  if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
    const originalSetupMiddlewares = devServerConfig.setupMiddlewares;

    devServerConfig.setupMiddlewares = (middlewares, devServer) => {
      // Call original setup if exists
      if (originalSetupMiddlewares) {
        middlewares = originalSetupMiddlewares(middlewares, devServer);
      }

      // Setup health endpoints
      setupHealthEndpoints(devServer, healthPluginInstance);

      return middlewares;
    };
  }

  return devServerConfig;
};

const configureDevServer = webpackConfig.devServer;
webpackConfig.devServer = (devServerConfig) =>
  makeDevServerV5Compatible(configureDevServer(devServerConfig));

module.exports = webpackConfig;

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  modularizeImports: {
    "lucide-react": {
      transform: "lucide-react/dist/esm/icons/{{kebabCase member}}",
    },
  },
};

module.exports = nextConfig;

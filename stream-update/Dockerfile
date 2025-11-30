FROM node:20-alpine

# Set working directory
WORKDIR /app

# Copy package.json and package-lock.json
COPY package.json ./

# Install dependencies
RUN npm install --production

# Copy script
COPY stream-update.js ./

# Expose port
EXPOSE 3001

# Run the script
CMD ["node", "stream-update.js"]

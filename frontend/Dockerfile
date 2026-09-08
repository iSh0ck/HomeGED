FROM node:24-alpine AS build
WORKDIR /app
# Le verrou est copié avec le manifeste : `npm ci` installe alors exactement les
# versions éprouvées, là où `npm install` peut ramener autre chose des semaines
# plus tard et faire diverger l'image de ce qui a été testé.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Vérification avant construction : un composant JSX non importé compile sans
# erreur mais plante à l'affichage. Mieux vaut une image qui refuse de se
# construire qu'un écran blanc chez l'utilisateur.
RUN npm run lint
# Tests de rendu : un composant qui ne se monte plus doit arrêter la
# construction, pas surprendre l'utilisateur à l'écran.
RUN npm test
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

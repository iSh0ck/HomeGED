import react from "eslint-plugin-react";
import hooks from "eslint-plugin-react-hooks";

/**
 * Vérification statique du frontend.
 *
 * Elle existe pour une raison précise : Vite compile sans broncher un composant
 * qui n'est pas importé. `<Pagination />` sans son `import` produit un bundle
 * valide qui plante à l'affichage, chez l'utilisateur, avec un écran blanc.
 * C'est arrivé deux fois ; d'où ce garde-fou, lancé à la construction de l'image.
 *
 * Deux règles portent l'essentiel :
 *   `no-undef`            variables et fonctions inconnues ;
 *   `react/jsx-no-undef`  composants JSX inconnus — que `no-undef` ne voit pas,
 *                         parce qu'il ne lit pas les balises.
 *   `react/jsx-no-duplicate-props`  même attribut deux fois sur un élément :
 *                         React garde le dernier en silence. Un `className`
 *                         répété avait ainsi supprimé une animation sans que
 *                         rien ne le signale.
 *
 *   `no-restricted-syntax`  deux pièges du système de langue (§22.56) : `t` lu
 *                         comme un objet — reste d'un paramètre renommé dont le
 *                         corps n'a pas suivi, qui rendait des libellés vides ;
 *                         et une variable nommée `t`, qui masque la fonction de
 *                         traduction dans toute sa portée.
 *
 * Le reste est volontairement en avertissement : le projet n'a pas vocation à
 * se plier à un style imposé, seulement à ne pas livrer de code qui ne peut pas
 * s'exécuter.
 */
export default [
  {
    files: ["**/*.{js,jsx}"],
    plugins: { react, "react-hooks": hooks },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: {
        window: "readonly", document: "readonly", navigator: "readonly",
        fetch: "readonly", console: "readonly",
        setTimeout: "readonly", clearTimeout: "readonly",
        setInterval: "readonly", clearInterval: "readonly",
        localStorage: "readonly", sessionStorage: "readonly",
        URL: "readonly", URLSearchParams: "readonly", Blob: "readonly",
        FormData: "readonly", FileReader: "readonly", File: "readonly",
        Image: "readonly", Intl: "readonly", AbortController: "readonly",
        MutationObserver: "readonly", ResizeObserver: "readonly",
        requestAnimationFrame: "readonly",
        alert: "readonly", confirm: "readonly",
      },
    },
    settings: { react: { version: "detect" } },
    rules: {
      "no-undef": "error",
      "react/jsx-no-undef": "error",
      "react/jsx-no-duplicate-props": "error",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "no-restricted-syntax": ["error",
        {
          selector: "MemberExpression[computed=false][object.name='t']",
          message: "« t » est la fonction de traduction : elle s'appelle, elle ne se lit pas. "
            + "Un « t.nom » est le reste d'un paramètre renommé — nommez la variable.",
        },
        {
          // `{ ...t }` : un répandage n'est pas un accès de propriété, et la
          // règle du dessus le laissait passer. C'est ainsi qu'un écran s'est
          // retrouvé à répandre la fonction de traduction dans son état (§22.85).
          selector: "SpreadElement > Identifier[name='t'], "
            + "RestElement > Identifier[name='t'], "
            + "JSXSpreadAttribute > Identifier[name='t']",
          message: "« t » est la fonction de traduction : la répandre ne donne rien. "
            + "C'est le reste d'un paramètre renommé — nommez la variable.",
        },
        {
          selector: ":matches(VariableDeclarator, FunctionDeclaration, ArrowFunctionExpression, "
            + "FunctionExpression, CatchClause) > Identifier[name='t']",
          message: "Ne nommez rien « t » : la fonction de traduction est importée sous ce nom "
            + "et se retrouverait masquée. Nommez la variable d'après ce qu'elle désigne.",
        },
      ],
    },
  },
  {
    // Là où `t` est *défini*, la règle qui interdit ce nom n'a pas de sens.
    files: ["src/lib/langue.js"],
    rules: { "no-restricted-syntax": "off" },
  },
  {
    // Les fichiers de test tournent dans jsdom, pas dans un navigateur : ils ont
    // leurs propres globales (`global` de Node, l'environnement de vitest, les
    // constructeurs du DOM qu'on bouchonne).
    files: ["**/*.test.{js,jsx}", "src/tests/**/*.js"],
    languageOptions: {
      globals: {
        global: "readonly", process: "readonly",
        Element: "readonly", Response: "readonly", Request: "readonly",
        describe: "readonly", it: "readonly", expect: "readonly",
        beforeEach: "readonly", afterEach: "readonly", vi: "readonly",
      },
    },
  },
];

/**
 * Genera `prototipo.html` — un archivo AUTOCONTENIDO que se abre con doble
 * clic y no necesita servidor, internet ni build en el navegador.
 *
 *   node docs/rediseno/construir.cjs
 *
 * Por qué autocontenido y no como la app real (React + Babel por CDN): un
 * prototipo que tarda dos segundos en pintar porque está compilando JSX en el
 * navegador no se juzga bien, y si el sitio donde se abre no tiene red se
 * queda en blanco. Aquí el JSX se compila ANTES y las librerías van dentro.
 *
 * Piezas de entrada, todas en esta carpeta:
 *   prototipo.src.html   la fuente con JSX y el marcador __CASOS_JSON__
 *   casos.json           tres análisis REALES sacados del motor
 *   react.js, react-dom.js   UMD de producción
 *
 * Sin tipografías remotas a propósito: un <link> a Google Fonts bloquea el
 * pintado cuando el archivo se abre sin red. Se usa la pila del sistema, que
 * es métricamente casi igual a Arimo. Lo que aquí se juzga es la disposición,
 * no la tipografía.
 *   tw.out.css           solo las clases de Tailwind que la fuente usa
 */
const fs = require('fs');
const path = require('path');

const DIR = __dirname;
const leer = f => fs.readFileSync(path.join(DIR, f), 'utf8');

function cargarBabel() {
    try { return require('@babel/standalone'); } catch (e) {}
    for (const base of [path.join(DIR, '..', '..'), process.env.SCRATCH || '']) {
        if (!base) continue;
        const p = path.join(base, 'node_modules', '@babel', 'standalone');
        if (fs.existsSync(p)) return require(p);
    }
    throw new Error('falta @babel/standalone (npm install @babel/standalone)');
}

const fuente = leer('prototipo.src.html');
const casos = leer('casos.json');

// 1. Inyectar los datos reales
let jsx = fuente.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
if (!jsx.includes('__CASOS_JSON__')) throw new Error('la fuente no tiene __CASOS_JSON__');
jsx = jsx.replace('__CASOS_JSON__', JSON.stringify(JSON.parse(casos)));

// 2. Compilar el JSX a JS normal
const { code } = cargarBabel().transform(jsx, {
    presets: [['react', { runtime: 'classic' }]],
    filename: 'prototipo.jsx',
});

// 3. Quedarse solo con el <style> propio de la fuente (Tailwind va aparte)
const estilos = fuente.match(/<style>([\s\S]*?)<\/style>/)[1];

const salida = `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Mentotrack — prueba de rediseño del diagnóstico</title>
<style>${leer('tw.out.css')}</style>
<style>${estilos}</style>
</head>
<body>
<div id="root"></div>
<script>${leer('react.js')}</script>
<script>${leer('react-dom.js')}</script>
<script>${code}</script>
</body>
</html>
`;

const destino = path.join(DIR, 'prototipo.html');
fs.writeFileSync(destino, salida, 'utf8');
console.log(`prototipo.html generado — ${Math.round(salida.length / 1024)} KB, sin dependencias externas`);

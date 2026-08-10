/**
 * Genera SOLO las clases de Tailwind que usa `prototipo.src.html`, para que el
 * prototipo no dependa del CDN (que compila en el navegador y tarda en pintar).
 *
 *   npx tailwindcss@3 -c docs/rediseno/tailwind.config.cjs \
 *       -i docs/rediseno/tw.in.css -o docs/rediseno/tw.out.css --minify
 *
 * Se escanea la FUENTE, no el archivo generado: partir del generado sería
 * circular y arrastraría clases que ya no se usan.
 */
module.exports = {
  content: [__dirname + '/prototipo.src.html'],
  theme: { extend: {} },
};

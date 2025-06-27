from typing import Optional, Any

import colorama
from ascii_magic import AsciiArt, Back, Front
from ascii_magic.asciimagic import Modes


class CustomAsciiArt(AsciiArt):
    CHARS_BY_DENSITY = ' .:-=+*#%@'

    @classmethod
    def from_image(cls, path: str) -> 'CustomAsciiArt':
        img = cls._load_file(path)
        return CustomAsciiArt(img)

    def to_ascii(
        self,
        columns: int = 120,
        width_ratio: float = 2.2,
        char: Optional[str] = None,
        monochrome: bool = False,
        back: Optional[Back] = None,
        front: Optional[Front] = None,
        debug: bool = False,
    ):
        art = self._img_to_art(
            columns=columns,
            width_ratio=width_ratio,
            char=char,
            monochrome=monochrome,
            back=back,
            front=front,
            debug=debug,
        )
        return art

    def _img_to_art(
        self,
        columns: int = 120,
        width_ratio: float = 2.2,
        char: Optional[str] = None,
        mode: Modes = Modes.TERMINAL,
        monochrome: bool = False,
        full_color: bool = True,
        back: Optional[Back] = None,
        front: Optional[Front] = None,
        debug: bool = False,
    ) -> str:
        if mode == Modes.TERMINAL:
            if monochrome:
                mode = Modes.ASCII

        if mode == Modes.HTML:
            if back or front:
                raise ValueError('Back or front colors not supported for HTML files')

            if monochrome:
                mode = Modes.HTML_MONOCHROME
            if not monochrome and not full_color:
                mode = Modes.HTML_TERMINAL

        if mode not in Modes:
            raise ValueError('Unknown output mode ' + str(mode))

        img_w, img_h = self._image.size
        scalar = img_w*width_ratio / columns
        img_w = int(img_w*width_ratio / scalar)
        img_h = int(img_h / scalar)
        rgb_img = self._image.resize((img_w, img_h))
        color_palette = self._image.getpalette()

        grayscale_img = rgb_img.convert("L")

        chars = [char] if char else self.CHARS_BY_DENSITY

        if debug:
            rgb_img.save('rgb.jpg')
            grayscale_img.save('grayscale.jpg')

        lines = []
        for h in range(img_h):
            line = ''

            for w in range(img_w):
                # get brightness value
                brightness = grayscale_img.getpixel((w, h)) / 255
                pixel = rgb_img.getpixel((w, h))
                # getpixel() may return an int, instead of tuple of ints, if the source img is a PNG with a transparency layer
                if isinstance(pixel, int):
                    pixel = (pixel, pixel, 255) if color_palette is None else tuple(color_palette[pixel*3:pixel*3 + 3])

                srgb = [(v/255.0)**2.2 for v in pixel]
                char = chars[int(brightness * (len(chars) - 1))]
                line += self._build_char(char, srgb, brightness, mode, front)

            if mode == Modes.TERMINAL and front:
                line = str(front) + line + colorama.Fore.RESET
            if mode == Modes.TERMINAL and back:
                line = str(back) + line + colorama.Back.RESET
            lines.append(line)

        if mode == Modes.TERMINAL:
            return '\n'.join(lines) + colorama.Fore.RESET
        elif mode == Modes.ASCII:
            return '\n'.join(lines)
        else:  # HTML modes
            return '<br />'.join(lines)

    def _build_char(
        self,
        char: str,
        srgb: list,
        brightness: float,
        mode: Modes = Modes.TERMINAL,
        front: Optional[Front] = None,
    ) -> str | None | Any:
        color = self._convert_color(srgb, brightness)

        if mode == Modes.TERMINAL:
            if front:
                return char  # Front color will be set per-line
            else:
                return color['term'] + char

        elif mode == Modes.ASCII:
            return char

        elif mode == Modes.HTML_TERMINAL:
            c = color['hex-term']
            return f'<span style="color: {c}">{char}</span>'

        elif mode == Modes.HTML:
            c = color['hex']
            return f'<span style="color: {c}">{char}</span>'

        elif mode == Modes.HTML_MONOCHROME:
            return f'<span style="color: white">{char}</span>'
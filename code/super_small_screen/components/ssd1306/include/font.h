/*
 * Minimal 5x7 ASCII font (32..126). Each glyph = 5 columns, 1 byte each,
 * plus 1 blank column rendered by the caller => 6 px advance.
 */
#ifndef FONT_H
#define FONT_H

#include <stdint.h>

extern const uint8_t font5x7[95][5];

#endif /* FONT_H */

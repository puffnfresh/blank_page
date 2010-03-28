from collections import defaultdict
import math
import random
try:
    import json
except ImportError:
    import simplejson as json

from pyglet.gl import *
from pyglet.sprite import Sprite
from pyglet.window import mouse
from pyglet.window import key
import pyglet
import data

# OpenAL and ALSA don't like my system - put them last
#pyglet.options['audio'] = ('directsound', 'silent', 'alsa', 'openal')

window = pyglet.window.Window(800, 600)
window.set_caption('Blank Page')

pyglet.resource.path.append(data.filepath(''))
pyglet.resource.reindex()

crosshair_image = pyglet.image.load(data.filepath('crosshair.png'))
crosshair = pyglet.window.ImageMouseCursor(crosshair_image, crosshair_image.width / 2, crosshair_image.height / 2)

GRAVITY = -300

TILE_SIZE = 48

tileset = [None,
           pyglet.resource.image('tile1.png'),
           pyglet.resource.image('tile2.png'),
           pyglet.resource.image('princess.png')]

TILE_PLAYER = -1
TILE_PRINCESS = 3
TILE_LAVA = 2

worlds = ['map1.json',
          'map2.json',
          'map3.json']

world_index = 0
world_offset = [0, 0]
world = None
world_map = None

map_width = None
map_height = None
map_batch = None

background_image = pyglet.image.load(data.filepath('background.gif'))
shoot_sound = pyglet.resource.media('shoot.wav', streaming=False)
bounce_sound = pyglet.resource.media('bounce.wav', streaming=False)
splat_sound = pyglet.resource.media('splat.wav', streaming=False)
dead_sound = pyglet.resource.media('death.wav', streaming=False)
finished_sound = pyglet.resource.media('finished.wav', streaming=False)

mouse_position = None
keys_pressed = defaultdict(lambda: False)

class Tile(Sprite):
    def __init__(self, index, x, y):
        self.animation = False

        image = tileset[index]

        if image.width > TILE_SIZE:
            self.animation = True
            self.sequence = pyglet.image.ImageGrid(image, 1, image.width / TILE_SIZE)

            self.tile_time = 0
            self.tile_frame = 0
            self.tile_speed = 0.25

            image = self.sequence[self.tile_frame]

        Sprite.__init__(self, image, x, y, batch=map_batch)
        self.xpos = x
        self.ypos = y

    def update(self, dt):
        self.x = self.xpos - world_offset[0]
        self.y = self.ypos - world_offset[1]

        if self.animation:
            self.tile_time += dt
            if self.tile_time >= self.tile_speed:
                self.tile_time -= self.tile_speed

                self.tile_frame += 1
                self.tile_frame %= len(self.sequence)

                self.image = self.sequence[self.tile_frame]
                

class Goo(Sprite):
    def __init__(self, x, y, dx, dy, goo_batch):
        image = pyglet.image.load(data.filepath('goo.png'))
        self.sequence = pyglet.image.ImageGrid(image, 1, 4)

        self.splat_image = pyglet.image.load(data.filepath('splat.png'))
        self.splat_image.anchor_x = self.splat_image.width / 2

        for sequence_image in self.sequence:
            sequence_image.anchor_x = sequence_image.width / 2
            sequence_image.anchor_y = sequence_image.height / 2

        Sprite.__init__(self, image, batch=goo_batch)
        self.x = self.xpos = x
        self.y = self.ypos = y

        self.speedx = dx
        self.speedy = dy

        self.animation_time = 0
        self.animation_frame = 0
        self.animation_speed = 0.25

        self.splat = False

        self.hitbox = (0, 0, self.splat_image.width, self.splat_image.height)

    def update(self, dt):
        if not self.visible:
            return

        self.x = self.xpos - world_offset[0]
        self.y = self.ypos - world_offset[1]

        if not self.splat:
            self.xpos += self.speedx * dt
            self.ypos += self.speedy * dt

            # Goo gets half gravity
            self.speedy += (GRAVITY / 2) * dt

            self.animation_time += dt
            if self.animation_time >= self.animation_speed:
                self.animation_frame += int(self.animation_time / self.animation_speed)
                self.animation_frame %= len(self.sequence)
                self.animation_time %= self.animation_speed

            self.image = self.sequence[self.animation_frame]

            x = self.xpos - 1
            y = self.ypos - 1

            collisions = collide_world(x, y, 2, 2)
            if collisions:
                if world_map[collisions[0]] in [TILE_LAVA, TILE_PRINCESS]:
                    self.visible = False
                    return

                self.splat = True
                splat_sound.play()

                surrounds = get_surrounds(collisions[0])

                tile_x = (collisions[0] % map_width) * TILE_SIZE + (TILE_SIZE / 2)
                tile_y = (collisions[0] / map_width) * TILE_SIZE + (TILE_SIZE / 2)

                if self.speedy < 0 and self.ypos > tile_y and not surrounds['top']:
                    self.ypos = tile_y + (TILE_SIZE / 2)
                elif self.speedy > 0 and self.ypos + self.image.anchor_y < tile_y and not surrounds['bottom']:
                    self.ypos = tile_y - (TILE_SIZE / 2)
                    self.rotation = 180
                elif self.xpos < tile_x and not surrounds['left']:
                    self.xpos = tile_x - (TILE_SIZE / 2)
                    self.rotation = -90
                elif self.xpos > tile_x and not surrounds['right']:
                    self.xpos = tile_x + (TILE_SIZE / 2)
                    self.rotation = 90

                self.image = self.splat_image


class Player(Sprite):
    def __init__(self):
        music_player.next()

        self.start_level()

        music_player.seek(0)
        music_player.play()

        bar_fill_image.width = bar_fill_image.start_width

        image = pyglet.image.load(data.filepath('player.png'))
        self.sequence = pyglet.image.ImageGrid(image, 5, 2)
        self.frame = -2

        for sequence_image in self.sequence:
            sequence_image.anchor_x = sequence_image.width / 2
            sequence_image.anchor_y = sequence_image.height / 2

        Sprite.__init__(self, self.sequence[self.frame], 0, window.height / 2)

        self.hitbox = (10, 2, 38, 30)

        # Start at 1, height - 1
        self.xpos = TILE_SIZE
        self.ypos = TILE_SIZE
        for index, value in enumerate(world_map):
            if value == TILE_PLAYER:
                self.xpos = (index % map_width) * TILE_SIZE
                self.ypos = ((index / map_width) + 1) * TILE_SIZE

        self.speedx = self.speedy = 0

        self.walking = False
        self.walk_speed = 100
        self.walk_damping = 0.1
        self.walk_frame_time = 0
        self.walk_frame_speed = 0.25

        self.goo_batch = pyglet.graphics.Batch()
        self.projectiles = []

        self.shoot_time = 0
        self.shoot_speed = 0.25
        self.shooting = False

        self.bounce_height = 400
        self.bounce_first = None

        self.finished = False
        self.dead = False

    def start_level(self):
        global text_overlay
        text_overlay.text = ''

        global world_index, world, world_map, world_offset

        world = json.load(data.load(worlds[world_index]))
        world_map = world['tiles']
        world_offset = [0, 0]

        global map_width, map_height, map_batch
        
        map_width = world['width']
        map_height = len(world_map) / map_width
        map_batch = pyglet.graphics.Batch()

        music_file = pyglet.resource.media(world['music'])
        music_player.queue(music_file)

        global tiles

        tiles = []
        for index, material in enumerate(world_map):
            if material and material > 0:
                tile = Tile(material, (index % map_width) * TILE_SIZE, (index / map_width) * TILE_SIZE)
                tiles.append(tile)

    def draw(self):
        if self.xpos > window.width / 2:
            self.x = window.width / 2
        else:
            self.x = self.xpos

        if self.ypos > window.height / 2:
            self.y = window.height / 2
        else:
            self.y = self.ypos

        Sprite.draw(self)

        self.goo_batch.draw()
        
    def shoot(self, x, y):
        if self.dead or self.finished:
            return

        if len(self.projectiles) >= world['max_goo']:
            return

        dx = x - self.x
        dy = y - self.y

        goo = Goo(self.xpos, self.ypos, dx, dy, self.goo_batch)
        shoot_sound.play()

        self.projectiles.append(goo)

        self.shooting = True

        goo_left = world['max_goo'] - len(self.projectiles)
        bar_fill_image.width = max((bar_fill_image.start_width / float(world['max_goo'])) * goo_left, 1)

    def update_offset(self):
        global world_offset
        world_offset = [self.xpos - (window.width / 2), self.ypos - (window.height / 2)]
        world_offset[0] = max(0, world_offset[0])
        world_offset[1] = max(0, world_offset[1])

    def update(self, dt):
        global player

        if self.dead:
            if keys_pressed[key.SPACE]:
                player = Player()

            self.speedy += GRAVITY * dt

            self.xpos += self.speedx * dt
            self.ypos += self.speedy * dt
            self.rotation += 180 * dt

            self.update_offset()

            for goo in self.projectiles:
                goo.update(dt)
            
            return

        if self.finished:
            if keys_pressed[key.SPACE]:
                global world_index
                world_index += 1

                if world_index >= len(worlds):
                    pyglet.app.exit()
                    return

                player = Player()

            self.rotation += 180 * dt

            return

        if self.walking:
            if keys_pressed[key.A]:
                self.speedx = -self.walk_speed
            elif keys_pressed[key.D]:
                self.speedx = self.walk_speed
            else:
                if self.speedx > 1:
                    self.speedx -= self.walk_speed * self.walk_damping
                elif self.speedx < -1:
                    self.speedx += self.walk_speed * self.walk_damping
                else:
                    self.speedx = 0
        else:
            if keys_pressed[key.A]:
                if self.speedx > -self.walk_speed:
                    self.speedx -= self.walk_speed * 3 * dt
                    self.speedx = max(self.speedx, -self.walk_speed)
            elif keys_pressed[key.D]:
                if self.speedx < self.walk_speed:
                    self.speedx += self.walk_speed * 3 * dt
                    self.speedx = min(self.speedx, self.walk_speed)

        oldx = self.xpos - self.image.anchor_x
        oldy = self.ypos - self.image.anchor_y

        self.xpos += self.speedx * dt

        if self.xpos < self.image.anchor_x:
            self.xpos = self.image.anchor_x
            self.speedx = 0

        if self.xpos > TILE_SIZE * map_width - self.image.anchor_x:
            self.xpos = TILE_SIZE * map_width - self.image.anchor_x
            self.speedx = 0

        self.speedy += GRAVITY * dt
        self.ypos += self.speedy * dt

        x = self.xpos - self.image.anchor_x
        y = self.ypos - self.image.anchor_y

        self.walking = False

        # Find the tile collisions
        collisions = collide_world(x + self.hitbox[0],
                                   y + self.hitbox[1],
                                   self.hitbox[2] - self.hitbox[0],
                                   self.hitbox[3] - self.hitbox[1])

        if collisions:
            for collision in collisions:
                surrounds = get_surrounds(collision)

                if world_map[collision] == TILE_PRINCESS:
                    self.frame = -1
                    self.finished = True
                    
                    music_player.pause()
                    finished_sound.play()

                    if world_index >= len(worlds) - 1:
                        text_overlay.text = "You won the game ^_^"
                    else:
                        text_overlay.text = "Weeeee, press space for next level"

                tile_x = (collision % map_width) * TILE_SIZE + (TILE_SIZE / 2)
                tile_y = (collision / map_width) * TILE_SIZE + (TILE_SIZE / 2)

                if self.speedy < 0 and oldy > tile_y and not surrounds['top']:
                    self.ypos = tile_y + (TILE_SIZE / 2) + self.image.anchor_y - self.hitbox[1]
                    self.speedy = 0
                    self.walking = True

                    if world_map[collision] == TILE_LAVA:
                        self.speedx = random.randint(-self.walk_speed, self.walk_speed)
                        self.speedy = random.randint(self.walk_speed, self.walk_speed * 2)
                        self.frame = -1
                        self.dead = True

                        music_player.pause()
                        dead_sound.play()

                        text_overlay.text = "YOU DIED. PRESS SPACE"

                elif self.speedy > 0 and oldy + TILE_SIZE < tile_y and not surrounds['bottom']:
                    self.ypos = tile_y - (TILE_SIZE / 2) - self.image.anchor_y + (self.image.height - self.hitbox[3])
                    self.speedy = 0

                elif self.speedx > 0 and oldx + TILE_SIZE < tile_x and not surrounds['left']:
                    self.xpos = tile_x - (TILE_SIZE / 2) - self.image.anchor_x + self.hitbox[0]
                    self.speedx = 0

                elif self.speedx < 0 and oldx > tile_x and not surrounds['right']:
                    self.xpos = tile_x + (TILE_SIZE / 2) + self.image.anchor_x - (self.image.width - self.hitbox[2])
                    self.speedx = 0

        if self.shooting:
            self.shoot_time += dt

            if self.walking:
                self.frame = -4
            else:
                self.frame = 0
                    
            if self.shoot_time >= self.shoot_speed:
                self.shoot_time = 0
                self.shooting = False

                if self.walking:
                    self.frame = -2
                else:
                    self.frame = 2

        elif self.walking:
            if self.frame not in [-1, -2]:
                self.frame = -1

            self.walk_frame_time += dt
            if self.walk_frame_time >= self.walk_frame_speed:
                if self.frame == -1:
                    self.frame = -2
                else:
                    self.frame = -1
                    
                self.walk_frame_time = 0

        else:
            self.frame = 2

        if self.walking:
            self.bounce_first = None

        self.image = self.sequence[self.frame]

        if mouse_position and mouse_position[0] < self.x:
            self.image = self.image.get_transform(flip_x = True)

        self.update_offset()

        for goo in self.projectiles:
            goo.update(dt)

            if goo.splat and goo.visible and collide_objects(self, goo):
                if self.bounce_first is None:
                    self.bounce_first = goo.rotation

                rotations = [goo.rotation]
                if math.fabs(goo.rotation - self.bounce_first) != 180:
                    rotations.append(self.bounce_first)

                for rotation in rotations:
                    if rotation == 180:
                        self.speedy = -self.bounce_height
                    elif rotation == -90:
                        self.speedx = -self.bounce_height
                    elif rotation == 90:
                        self.speedx = self.bounce_height
                    else:
                        self.speedy = self.bounce_height

                bounce_sound.play()


def get_surrounds(index):
    surrounds = {}
    
    if index % map_width > 0:
        surrounds['left'] = world_map[index - 1]
        if surrounds['left'] < 0:
            surrounds['left'] = None
    else:
        surrounds['left'] = None
        
    if index % map_width < map_width - 1:
        surrounds['right'] = world_map[index + 1]
        if surrounds['right'] < 0:
            surrounds['right'] = None
    else:
        surrounds['right'] = None

    if index < len(world_map) - map_width:
        surrounds['top'] = world_map[index + map_width]
        if surrounds['top'] < 0:
            surrounds['top'] = None
    else:
        surrounds['top'] = None

    if index > map_width:
        surrounds['bottom'] = world_map[index - map_width]
        if surrounds['bottom'] < 0:
            surrounds['bottom'] = None
    else:
        surrounds['bottom'] = None

    return surrounds

def collide_objects(a, b):
    a_x1 = a.xpos - a.image.anchor_x + a.hitbox[0]
    a_x2 = a_x1 + (a.hitbox[2] - a.hitbox[0])
    a_y1 = a.ypos - a.image.anchor_y + a.hitbox[1]
    a_y2 = a_y1 + (a.hitbox[3] - a.hitbox[1])

    b_x1 = b.xpos - b.image.anchor_x + b.hitbox[0]
    b_x2 = b_x1 + (b.hitbox[2] - b.hitbox[0])
    b_y1 = b.ypos - b.image.anchor_y + b.hitbox[1]
    b_y2 = b_y1 + (b.hitbox[3] - b.hitbox[1])

    if a_x1 > b_x2:
        return False

    if a_x2 < b_x1:
        return False

    if a_y1 > b_y2:
        return False

    if a_y2 < b_y1:
        return False

    return True

def collide_world(x, y, width, height):
    collisions = []

    world_x1 = int(math.floor(x / float(TILE_SIZE)))
    world_x2 = int(math.ceil((x + width) / float(TILE_SIZE)))
    world_y1 = int(math.floor(y / float(TILE_SIZE)))
    world_y2 = int(math.ceil((y + height) / float(TILE_SIZE)))

    for i in range(world_y1, world_y2):
        y_index = i * map_width

        if y_index < 0 or y_index >= len(world_map):
            continue

        if world_x2 < 0 or world_x1 >= map_width:
            continue

        for index in range(y_index + world_x1, y_index + world_x2):
            tile = world_map[index]
            if tile and tile > 0:
                collisions.append(index)

    return collisions

text_overlay = pyglet.text.Label("", font_size=30)
text_overlay.anchor_x = text_overlay.anchor_y = 'center'
text_overlay.x = window.width / 2
text_overlay.y = window.height / 2

music_player = pyglet.media.Player()
music_player.eos_action = music_player.EOS_LOOP

intro = True

intro_player = pyglet.media.Player()

bar_outline_image = pyglet.resource.image('bar_outline.png')
bar_outline = Sprite(bar_outline_image, 10, 10)

bar_fill_image = pyglet.resource.image('bar_fill.gif')
bar_fill_image.anchor_y = bar_fill_image.height / 2
bar_fill_image.start_width = 135

tiles = None

player = None

@window.event
def on_draw():
    window.clear()

    if intro:
        texture = intro_player.get_texture()
        if texture:
            texture.blit(0, 0)
    else:
        background_image.blit(0, 0)
        map_batch.draw()
        player.draw()

        bar_fill_image.blit(bar_outline.x + 4, bar_outline.y + (bar_outline.height / 2))
        bar_outline.draw()

        text_overlay.draw()

@window.event
def on_key_press(symbol, modifiers):
    if intro:
        return

    keys_pressed[symbol] = True

@window.event
def on_key_release(symbol, modifiers):
    if intro:
        return

    keys_pressed[symbol] = False

@window.event
def on_mouse_motion(x, y, dx, dy):
    if intro:
        return

    global mouse_position
    mouse_position = (x, y)

@window.event
def on_mouse_press(x, y, buttons, modifiers):
    if intro:
        intro_player.pause()
        on_eos()
        return

    if buttons == mouse.LEFT:
        player.shoot(x, y)

def update(dt):
    if intro:
        return

    player.update(dt)

    for tile in tiles:
        tile.update(dt)

# This is fired after the intro video
@intro_player.event
def on_eos():
    global intro
    intro = False

    window.set_mouse_cursor(crosshair)
    pyglet.clock.schedule_interval(update, 1/60.0)

    global player
    player = Player()

if pyglet.media.have_avbin:
    intro_video = pyglet.resource.media('intro.avi')
    intro_player.queue(intro_video)
    intro_player.play()
else:
    on_eos()

def main():
    pyglet.app.run()

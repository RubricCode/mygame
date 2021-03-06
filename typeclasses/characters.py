"""
Characters

Characters are (by default) Objects setup to be puppeted by Accounts.
They are what you "see" in game. The Character class in this module
is setup to be the "default" character type created by the default
creation commands.

"""
from random import randint
from evennia import TICKER_HANDLER as tickerhandler
from evennia.utils import lazy_property
from world.equip import EquipHandler
from evennia.contrib.rpg.traits import TraitHandler
from evennia.contrib.game_systems.gendersub import GenderCharacter
from commands import chartraits, equip
from world.rulebook import parse_health
from world.traitcalcs import abilitymodifiers, calculate_secondary_traits
from world.death import CharDeathHandler
from math import floor
from evennia.server.sessionhandler import SESSIONS


traits = {
    # primary
    'STR': {'base': 3, 'mod': 0, 'mult': 1, 'name': 'Strength', 'trait_type': 'static'}, 
    'DEX': {'base': 3, 'mod': 0, 'mult': 1, 'name': 'Dexterity', 'trait_type': 'static'}, 
    'CON': {'base': 3, 'mod': 0, 'mult': 1, 'name': 'Constitution', 'trait_type': 'static'}, 
    'INT': {'base': 3, 'mod': 0, 'mult': 1, 'name': 'Intelligence', 'trait_type': 'static'}, 
    'WIS': {'base': 3, 'mod': 0, 'mult': 1, 'name': 'Wisdom', 'trait_type': 'static'}, 
    'CHA': {'base': 3, 'mod': 0, 'mult': 1, 'name': 'Charisma', 'trait_type': 'static'}, 
    # secondary
    'HP': {'base': 100, 'min': 0, 'max': None, 'name': 'Health', 'trait_type': 'gauge', 'mult': 1.0, 'rate': 0,
           'ratetarget': None, 'mod': 0, 'descs': None, 'last_update': None, 'current': 100.0},
    'SP': {'base': 100, 'min': 0, 'max': None, 'name': 'Spell Power', 'trait_type': 'gauge', 'mult': 1.0, 'rate': 0,
           'ratetarget': None, 'mod': 0, 'descs': None, 'last_update': None, 'current': 100.0},
    'EP': {'base': 100, 'min': 0, 'max': None, 'name': 'Endurance', 'trait_type': 'gauge', 'mult': 1.0, 'rate': 0,
           'ratetarget': None, 'mod': 0, 'descs': None, 'last_update': None, 'current': 100.0},
    # saves
    'FORT': {'base': 0, 'mod': 0, 'mult': 1, 'name': 'Fortitude Save', 'trait_type': 'static'},
    'REFL': {'base': 0, 'mod': 0, 'mult': 1, 'name': 'Reflex Save', 'trait_type': 'static'},
    'WILL': {'base': 0, 'mod': 0, 'mult': 1, 'name': 'Willpower Save', 'trait_type': 'static'},

    # combat
    'MAB': {'base': 0, 'mod': 0, 'mult': 1, 'name': 'Melee Attack Bonus', 'trait_type': 'static'},
    'RAB': {'base': 0, 'mod': 0, 'mult': 1, 'name': 'Ranged Attack Bonus', 'trait_type': 'static'},
    'UAB': {'base': 0, 'mod': 0, 'mult': 1, 'name': 'Unarmed Attack Bonus', 'trait_type': 'static'},
    'FAB': {'base': 0, 'mod': 0, 'mult': 1, 'name': 'Finesse Attack Bonus', 'trait_type': 'static'},
    'PDEF': {'base': 10, 'mod': 0, 'mult': 1, 'name': 'Physical Defense', 'trait_type': 'static'},
    'MDEF': {'base': 10, 'mod': 0, 'mult': 1, 'name': 'Magical Defense', 'trait_type': 'static'},

    # misc
    'LVL': {'base': 1, 'mod': 0, 'mult': 1, 'name': 'Level', 'trait_type': 'static'},
    'ENC': {'base': 0, 'mod': 0, 'min': 0, 'max': 0, 'name': 'Carry Weight', 'trait_type': 'counter',
            'ratetarget': None, 'mult': 1.0, 'descs': None, 'rate': 0, 'last_update': None},
    'XP': {'base': 0, 'mod': 0, 'min': 0, 'max': None, 'name': 'Experience', 'trait_type': 'counter',
           'ratetarget': None, 'mult': 1.0, 'descs': None, 'rate': 0, 'last_update': None},
}


wield_slots = ['wield1', 'wield2']
armor_slots = ['helm', 'necklace', 'cloak', 'torso',
               'belt', 'bracers', 'gloves', 'ring1', 'ring2', 'boots']
clothing_slots = ['hat', 'accessory', 'overtop', 'bottom', 'belt2', 'accessory2',
                  'gloves2', 'accessory3', 'accessory4', 'shoes']


class Character(GenderCharacter):
    """
    The Character defaults to reimplementing some of base Object's hook methods with the
    following functionality:

    at_basetype_setup - always assigns the DefaultCmdSet to this object type
                (important!)sets locks so character cannot be picked up
                and its commands only be called by itself, not anyone else.
                (to change things, use at_object_creation() instead).
    at_after_move(source_location) - Launches the "look" command after every move.
    at_post_unpuppet(account) -  when Account disconnects from the Character, we
                store the current location in the pre_logout_location Attribute and
                move it to a None-location so the "unpuppeted" character
                object does not need to stay on grid. Echoes "Account has disconnected"
                to the room.
    at_pre_puppet - Just before Account re-connects, retrieves the character's
                pre_logout_location Attribute and move it back on the grid.
    at_post_puppet - Echoes "AccountName has entered the game" to the room.
    """

    def announce_move_from(self, destination, msg=None, mapping=None):
        """
         Called if the move is to be announced. This is
         called while we are still standing in the old
         location.

         Args:
             destination (Object): The place we are going to.
             msg (str, optional): a replacement message.
             mapping (dict, optional): additional mapping objects.

         You can override this method and call its parent with a
         message to simply change the default message.  In the string,
         you can use the following as mappings (between braces):
             object: the object which is moving.
             exit: the exit from which the object is moving (if found).
             origin: the location of the object before the move.
             destination: the location of the object after moving.

        """
        if not self.location:
            return
        if msg:
            string = msg
        else:
            string = "{object} leaves {exit}."

        location = self.location
        exits = [o for o in location.contents if o.location is location and o.destination is destination]
        if not mapping:
            mapping = {}

        mapping.update({
            "object": self,
            "exit": exits[0] if exits else "somwhere",
            "origin": location or "nowhere",
            "destination": destination or "nowhere", })

        location.msg_contents(string, exclude=(self,), mapping=mapping)

    def announce_move_to(self, source_location, msg=None, mapping=None):
        """
         Called after the move if the move was not quiet. At this point
         we are standing in the new location.

         Args:
             source_location (Object): The place we came from
             msg (str, optional): the replacement message if location.
             mapping (dict, optional): additional mapping objects.

         You can override this method and call its parent with a
         message to simply change the default message.  In the string,
         you can use the following as mappings (between braces):
             object: the object which is moving.
             exit: the exit from which the object is moving (if found).
             origin: the location of the object before the move.
             destination: the location of the object after moving.

         """

        if not source_location and self.location.has_account:
            # This was created from nowhere and added to an account's
            # inventory; it's probably the result of a create command.
            string = "You now have %s in your possession." % self.get_display_name(self.location)
            self.location.msg(string)
            return

        if source_location:
            if msg:
                string = msg
            else:
                string = "{object} arrives from the {exit}."
        else:
            string = "{object} arrives to {destination}."

        origin = source_location
        destination = self.location
        exits = []
        if origin:
            exits = [o for o in destination.contents if o.location is destination and o.destination is origin]

        if not mapping:
            mapping = {}

        mapping.update({
            "object": self,
            "exit": exits[0] if exits else "somewhere",
            "origin": origin or "nowhere",
            "destination": destination or "nowhere",
        })

        destination.msg_contents(string, exclude=(self,), mapping=mapping)

    def at_object_creation(self):
        super(Character, self).at_object_creation()
        self.db.gender = 'ambiguous'
        self.db.nation = ""
        self.db.race = 'Wisp'
        self.db.background = ""
        self.db.guild = None
        self.db.clan = ""
        self.db.profession = ""
        self.db.title = ""
        self.db.faith = ""
        self.db.devotion = ""
        self.db.desc = "A small wisp of energy lacking in any discernible features, all that is missing is the " \
                       "spark of creation."
        self.db.smellable_text = "You don't smell anything special."
        self.db.feelable_text = "You don't feel anything special."
        self.db.tasteable_text = "You don't taste anything special."
        self.db.bank = 0
        self.db.wallet = 0

        self.db.permadeath = False
        self.db.descSet = False
        self.db.backSet = False
        self.db.statSet = False
        self.db.is_in_creation = True
        self.db.carry_factor = 10
        self.db.lift_factor = 20
        self.db.push_factor = 40
        # self.db.is_in_combat = False
        # self.db.is_immobile = False

        for key, kwargs in traits.items():
            self.traits.add(key, **kwargs)

        calculate_secondary_traits(self.traits)

        self.traits.ENC.max = self.db.lift_factor * self.traits.STR.value

        self.db.slots = {
            # armor slots
            'wield1': None,
            'wield2': None,
            'helm': None,
            'necklace': None,
            'cloak': None,
            'torso': None,
            'belt': None,
            'bracers': None,
            'gloves': None,
            'ring1': None,
            'ring2': None,
            'boots': None,
            # clothing slots
            'hat': None,
            'accessory': None,
            'overtop': None,
            'top': None,
            'bottom': None,
            'belt2': None,
            'accessory2': None,
            'gloves2': None,
            'accessory3': None,
            'accessory4': None,
            'shoes': None,
        }

        tickerhandler.add(interval=randint(10, 15), callback=self.at_regen, persistent=True)

    def at_post_puppet(self):
        self.location.msg_contents("%s has connected" % self.key)
        loginmsg = "[************--World Crier--************]|/" \
                   "     %s arrives in Ayacia.|/" \
                   "[***************************************]|/" % self.key
        SESSIONS.announce_all(loginmsg)
        tickerhandler.add(interval=randint(10, 15), callback=self.at_regen, persistent=True)
        self.execute_cmd("look")

    @lazy_property
    def traits(self):
        return TraitHandler(self)

#    @lazy_property
#    def skills(self, ):
#        return TraitHandler(self, db_attribute='skills')

    @lazy_property
    def equip(self):
        """Handler for equipped items."""
        return EquipHandler(self)

    def at_regen(self):
        """Hook called by a 12s ticker"""
        self.traits.HP.current += int(floor(0.1 * self.traits.HP.max))
        self.traits.SP.current += int(floor(0.1 * self.traits.SP.max))
        self.traits.EP.current += int(floor(0.1 * self.traits.EP.max))

    def at_death(self):
        """Hook called when a character dies"""
        self.scripts.add(CharDeathHandler)

    def return_appearance(self, looker):
        if not looker:
            return

        looker.msg("|S is %s.|/" % parse_health(self))
        looker.msg("You see a %s %s,|/" % (self.db.gender, self.db.race))
        looker.msg("%s" % self.db.desc)
        looker.msg("|S has %s.|/" % self.db.hairdesc)
        looker.msg("|S has %s.|/" % self.db.eyedesc)

        equip_message = """
        Wielding: {wielding}
        Armors: {armor}
        Clothing: {clothing}""".format(
            wielding="\n\t  ".join(
                [self.equip.get(slot).get_display_name(looker) for slot in wield_slots if self.equip.get(slot)]),
            armor="\n\t  ".join(
                [self.equip.get(slot).get_display_name(looker) for slot in armor_slots if self.equip.get(slot)]),
            clothing="\n\t  ".join(
                [self.equip.get(slot).get_display_name(looker) for slot in clothing_slots if self.equip.get(slot)]))
        looker.msg(equip_message)

    def at_object_receive(self, obj, source):
        if not obj.db.weight:
            return
        else:
            self.traits.ENC.current += obj.db.weight
            self.traits.EP.mod = \
                int(-(self.traits.ENC.actual // (2 * self.traits.STR.actual)))

    def at_object_leave(self, obj, source):
        if not obj.db.weight:
            return
        else:
            self.traits.ENC.current -= obj.db.weight
            self.traits.EP.mod = \
                int(+(self.traits.ENC.actual // (2 * self.traits.STR.actual)))


class NPC(Character):
    """Base character typeclass for NPCs and enemies.
       """

    def at_object_creation(self):
        super(NPC, self).at_object_creation()

        self.db.emote_aggressive = "stares about angrily"

        self.db.slots = {'wield': None,
                         'armor': None}

        # initialize traits
        for key, kwargs in npc.traits.items():
            self.traits.add(key, **kwargs)

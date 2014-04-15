# * encoding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals

from unittest import TestCase as UnitTestCase
try:
    from unittest import skipIf, skipUnless
except:
    from django.utils.unittest import skipIf, skipUnless

import django
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core import serializers
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import six
from django.utils.encoding import force_text

from django.contrib.contenttypes.models import ContentType

from taggit.managers import TaggableManager, _TaggableManager, _model_name
from taggit.models import Tag, TaggedItem
from .forms import (FoodForm, DirectFoodForm, CustomPKFoodForm,
    OfficialFoodForm)
from .models import (Food, Pet, HousePet, DirectFood, DirectPet,
    DirectHousePet, TaggedPet, CustomPKFood, CustomPKPet, CustomPKHousePet,
    TaggedCustomPKPet, OfficialFood, OfficialPet, OfficialHousePet,
    OfficialThroughModel, OfficialTag, Photo, Movie, Article, CustomManager)
from taggit.utils import parse_tags, edit_string_for_tags


class BaseTaggingTest(object):
    def assert_tags_equal(self, qs, tags, sort=True, attr="name"):
        got = [getattr(obj, attr) for obj in qs]
        if sort:
            got.sort()
            tags.sort()
        self.assertEqual(got, tags)

    def _get_form_str(self, form_str):
        if django.VERSION >= (1, 3):
            form_str %= {
                "help_start": '<span class="helptext">',
                "help_stop": "</span>"
            }
        else:
            form_str %= {
                "help_start": "",
                "help_stop": ""
            }
        return form_str

    def assert_form_renders(self, form, html):
        self.assertHTMLEqual(str(form), self._get_form_str(html))


class BaseTaggingTestCase(TestCase, BaseTaggingTest):
    pass


class BaseTaggingTransactionTestCase(TransactionTestCase, BaseTaggingTest):
    pass


class TagModelTestCase(BaseTaggingTransactionTestCase):
    food_model = Food
    tag_model = Tag

    def test_unique_slug(self):
        apple = self.food_model.objects.create(name="яблоко")
        apple.tags.add("Красное", "красное")

    def test_update(self):
        special = self.tag_model.objects.create(name="специальный")
        special.save()

    def test_add(self):
        apple = self.food_model.objects.create(name="яблоко")
        yummy = self.tag_model.objects.create(name="вкусное")
        apple.tags.add(yummy)

    def test_slugify(self):
        a = Article.objects.create(title="django-taggit 1.0 Released")
        a.tags.add("великолепный", "релиз", "ВЕЛИКОЛЕПНЫЙ")
        self.assert_tags_equal(a.tags.all(), [
            "category-великолепный",
            "category-релиз",
            "category-великолепный-1"
        ], attr="slug")

class TagModelDirectTestCase(TagModelTestCase):
    food_model = DirectFood
    tag_model = Tag

class TagModelCustomPKTestCase(TagModelTestCase):
    food_model = CustomPKFood
    tag_model = Tag

class TagModelOfficialTestCase(TagModelTestCase):
    food_model = OfficialFood
    tag_model = OfficialTag

class TaggableManagerTestCase(BaseTaggingTestCase):
    food_model = Food
    pet_model = Pet
    housepet_model = HousePet
    taggeditem_model = TaggedItem
    tag_model = Tag

    def test_add_tag(self):
        apple = self.food_model.objects.create(name="яблоко")
        self.assertEqual(list(apple.tags.all()), [])
        self.assertEqual(list(self.food_model.tags.all()),  [])

        apple.tags.add('зеленый')
        self.assert_tags_equal(apple.tags.all(), ['зеленый'])
        self.assert_tags_equal(self.food_model.tags.all(), ['зеленый'])

        pear = self.food_model.objects.create(name="груша")
        pear.tags.add('зеленый')
        self.assert_tags_equal(pear.tags.all(), ['зеленый'])
        self.assert_tags_equal(self.food_model.tags.all(), ['зеленый'])

        apple.tags.add('красный')
        self.assert_tags_equal(apple.tags.all(), ['зеленый', 'красный'])
        self.assert_tags_equal(self.food_model.tags.all(), ['зеленый', 'красный'])

        self.assert_tags_equal(
            self.food_model.tags.most_common(),
            ['зеленый', 'красный'],
            sort=False
        )

        apple.tags.remove('зеленый')
        self.assert_tags_equal(apple.tags.all(), ['красный'])
        self.assert_tags_equal(self.food_model.tags.all(), ['зеленый', 'красный'])
        tag = self.tag_model.objects.create(name="вкусный")
        apple.tags.add(tag)
        self.assert_tags_equal(apple.tags.all(), ["красный", "вкусный"])

        apple.delete()
        self.assert_tags_equal(self.food_model.tags.all(), ["зеленый"])

    def test_add_queries(self):
        # Prefill content type cache:
        ContentType.objects.get_for_model(self.food_model)
        apple = self.food_model.objects.create(name="яблоко")
        #   1  query to see which tags exist
        # + 3  queries to create the tags.
        # + 6  queries to create the intermediary things (including SELECTs, to
        #      make sure we don't double create.
        # + 12 on Django 1.6 for save points.
        queries = 22
        if django.VERSION < (1,6):
            queries -= 12
        self.assertNumQueries(queries, apple.tags.add, "красный", "вкусный", "зеленый")

        pear = self.food_model.objects.create(name="груша")
        #   1 query to see which tags exist
        # + 4 queries to create the intermeidary things (including SELECTs, to
        #     make sure we dont't double create.
        # + 4 on Django 1.6 for save points.
        queries = 9
        if django.VERSION < (1,6):
            queries -= 4
        self.assertNumQueries(queries, pear.tags.add, "зеленый", "вкусный")

        self.assertNumQueries(0, pear.tags.add)

    def test_require_pk(self):
        food_instance = self.food_model()
        self.assertRaises(ValueError, lambda: food_instance.tags.all())

    def test_delete_obj(self):
        apple = self.food_model.objects.create(name="яблоко")
        apple.tags.add("красный")
        self.assert_tags_equal(apple.tags.all(), ["красный"])
        strawberry = self.food_model.objects.create(name="клубника")
        strawberry.tags.add("красный")
        apple.delete()
        self.assert_tags_equal(strawberry.tags.all(), ["красный"])

    def test_delete_bulk(self):
        apple = self.food_model.objects.create(name="яблоко")
        kitty = self.pet_model.objects.create(pk=apple.pk,  name="котенок")

        apple.tags.add("красный", "вкусный", "фрукт")
        kitty.tags.add("кошка")

        self.food_model.objects.all().delete()

        self.assert_tags_equal(kitty.tags.all(), ["кошка"])

    def test_lookup_by_tag(self):
        apple = self.food_model.objects.create(name="яблоко")
        apple.tags.add("красный", "зеленый")
        pear = self.food_model.objects.create(name="груша")
        pear.tags.add("зеленый")
        self.assertEqual(
            list(self.food_model.objects.filter(tags__name__in=["красный"])),
            [apple]
        )
        self.assertEqual(
            list(self.food_model.objects.filter(tags__name__in=["зеленый"])),
            [apple, pear]
        )

        kitty = self.pet_model.objects.create(name="котенок")
        kitty.tags.add("мутный", "красный")
        dog = self.pet_model.objects.create(name="собака")
        dog.tags.add("гав", "красный")
        self.assertEqual(
            list(self.food_model.objects.filter(tags__name__in=["красный"]).distinct()),
            [apple]
        )

        tag = self.tag_model.objects.get(name="гав")
        self.assertEqual(list(self.pet_model.objects.filter(tags__in=[tag])), [dog])

        cat = self.housepet_model.objects.create(name="кот", trained=True)
        cat.tags.add("мутный")

        pks = self.pet_model.objects.filter(tags__name__in=["мутный"])
        model_name = self.pet_model.__name__
        self.assertQuerysetEqual(pks,
            [u'<{0}: котенок>'.format(model_name),
             u'<{0}: кот>'.format(model_name)],
            ordered=False)

    def test_lookup_bulk(self):
        apple = self.food_model.objects.create(name="яблоко")
        pear = self.food_model.objects.create(name="груша")
        apple.tags.add('фрукт', 'зеленый')
        pear.tags.add('фрукт', 'вкусный')

        def lookup_qs():
            # New fix: directly allow WHERE object_id IN (SELECT id FROM ..)
            objects = self.food_model.objects.all()
            lookup = self.taggeditem_model.bulk_lookup_kwargs(objects)
            list(self.taggeditem_model.objects.filter(**lookup))

        def lookup_list():
            # Simulate old situation: iterate over a list.
            objects = list(self.food_model.objects.all())
            lookup = self.taggeditem_model.bulk_lookup_kwargs(objects)
            list(self.taggeditem_model.objects.filter(**lookup))

        self.assertNumQueries(1, lookup_qs)
        self.assertNumQueries(2, lookup_list)

    def test_exclude(self):
        apple = self.food_model.objects.create(name="яблоко")
        apple.tags.add("красный", "зеленый", "вкусный")

        pear = self.food_model.objects.create(name="груша")
        pear.tags.add("зеленый", "вкусный")

        guava = self.food_model.objects.create(name="гуава")

        pks = self.food_model.objects.exclude(tags__name__in=["красный"])
        model_name = self.food_model.__name__
        self.assertQuerysetEqual(pks,
            ['<{0}: груша>'.format(model_name),
             '<{0}: гуава>'.format(model_name)],
            ordered=False)

    def test_similarity_by_tag(self):
        """Test that pears are more similar to apples than watermelons"""
        apple = self.food_model.objects.create(name="яблоко")
        apple.tags.add("зеленый", "сочный", "маленький", "кислый")

        pear = self.food_model.objects.create(name="груша")
        pear.tags.add("зеленый", "сочный", "маленький", "сладкий")

        watermelon = self.food_model.objects.create(name="арбуз")
        watermelon.tags.add("зеленый", "сочный", "большой", "сладкий")

        similar_objs = apple.tags.similar_objects()
        self.assertEqual(similar_objs, [pear, watermelon])
        self.assertEqual([obj.similar_tags for obj in similar_objs],
                         [3, 2])

    def test_tag_reuse(self):
        apple = self.food_model.objects.create(name="яблоко")
        apple.tags.add("сочный", "сочный")
        self.assert_tags_equal(apple.tags.all(), ['сочный'])

    def test_query_traverse(self):
        spot = self.pet_model.objects.create(name='Спот')
        spike = self.pet_model.objects.create(name='Спайк')
        spot.tags.add('страшный')
        spike.tags.add('пушистый')
        lookup_kwargs = {
            '%s__name' % _model_name(self.pet_model): 'Спот'
        }
        self.assert_tags_equal(
           self.tag_model.objects.filter(**lookup_kwargs),
           ['страшный']
        )

    def test_taggeditem_unicode(self):
        ross = self.pet_model.objects.create(name="росс")
        # I keep Ross Perot for a pet, what's it to you?
        ross.tags.add("президент")

        self.assertEqual(
            force_text(self.taggeditem_model.objects.all()[0]),
            "росс tagged with президент"
        )

    def test_abstract_subclasses(self):
        p = Photo.objects.create()
        p.tags.add("уличный", "красивый")
        self.assert_tags_equal(
            p.tags.all(),
            ["уличный", "красивый"]
        )

        m = Movie.objects.create()
        m.tags.add("вк")
        self.assert_tags_equal(
            m.tags.all(),
            ["вк"],
        )

    def test_field_api(self):
        # Check if tag field, which simulates m2m, has django-like api.
        field = self.food_model._meta.get_field('tags')
        self.assertTrue(hasattr(field, 'rel'))
        self.assertTrue(hasattr(field, 'related'))
        self.assertEqual(self.food_model, field.related.model)

    def test_names_method(self):
        apple = self.food_model.objects.create(name="яблоко")
        apple.tags.add('зеленый')
        apple.tags.add('красный')
        self.assertEqual(list(apple.tags.names()), ['зеленый', 'красный'])

    def test_slugs_method(self):
        apple = self.food_model.objects.create(name="яблоко")
        apple.tags.add('зеленый и сочный')
        apple.tags.add('красный')
        self.assertEqual(list(apple.tags.slugs()), ['zelenyij-i-sochnyij', 'krasnyij'])

    def test_serializes(self):
        apple = self.food_model.objects.create(name="яблоко")
        serializers.serialize("json", (apple,))

    def test_prefetch_related(self):
        apple = self.food_model.objects.create(name="яблоко")
        apple.tags.add('1', '2')
        orange = self.food_model.objects.create(name="апельсин")
        orange.tags.add('2', '4')
        with self.assertNumQueries(2):
            l = list(self.food_model.objects.prefetch_related('tags').all())
        with self.assertNumQueries(0):
            foods = dict((f.name, set(t.name for t in f.tags.all())) for f in l)
            self.assertEqual(foods, {
                'апельсин': set(['2', '4']),
                'яблоко': set(['1', '2'])
            })

class TaggableManagerDirectTestCase(TaggableManagerTestCase):
    food_model = DirectFood
    pet_model = DirectPet
    housepet_model = DirectHousePet
    taggeditem_model = TaggedPet

class TaggableManagerCustomPKTestCase(TaggableManagerTestCase):
    food_model = CustomPKFood
    pet_model = CustomPKPet
    housepet_model = CustomPKHousePet
    taggeditem_model = TaggedCustomPKPet

    def test_require_pk(self):
        # TODO with a charfield pk, pk is never None, so taggit has no way to
        # tell if the instance is saved or not
        pass

class TaggableManagerOfficialTestCase(TaggableManagerTestCase):
    food_model = OfficialFood
    pet_model = OfficialPet
    housepet_model = OfficialHousePet
    taggeditem_model = OfficialThroughModel
    tag_model = OfficialTag

    def test_extra_fields(self):
        self.tag_model.objects.create(name="красный")
        self.tag_model.objects.create(name="вкусный", official=True)
        apple = self.food_model.objects.create(name="яблоко")
        apple.tags.add("вкусный", "красный")

        pear = self.food_model.objects.create(name="Груша")
        pear.tags.add("вкусный")

        self.assertEqual(apple, self.food_model.objects.get(tags__official=False))

class TaggableManagerInitializationTestCase(TaggableManagerTestCase):
    """Make sure manager override defaults and sets correctly."""
    food_model = Food
    custom_manager_model = CustomManager

    def test_default_manager(self):
        self.assertEqual(self.food_model.tags.__class__, _TaggableManager)

    def test_custom_manager(self):
        self.assertEqual(self.custom_manager_model.tags.__class__, CustomManager.Foo)

class TaggableFormTestCase(BaseTaggingTestCase):
    form_class = FoodForm
    food_model = Food

    # def test_form(self):
    #     self.assertEqual(list(self.form_class.base_fields), ['name', 'tags'])
    #
    #     f = self.form_class({'name': 'яблоко', 'tags': 'зеленый, красный, вкусный'})
    #     self.assert_form_renders(f, """<tr><th><label for="id_name">Name:</label></th><td><input id="id_name" type="text" name="name" value="яблоко" maxlength="50" /></td></tr><tr><th><label for="id_tags">Tags:</label></th><td><input type="text" name="tags" value="зеленый, красный, вкусный" id="id_tags" /><br />%(help_start)sA comma-separated list of tags.%(help_stop)s</td></tr>""")
    #     f.save()
    #     apple = self.food_model.objects.get(name='яблоко')
    #     self.assert_tags_equal(apple.tags.all(), ['зеленый', 'красный', 'вкусный'])
    #
    #     f = self.form_class({'name': 'яблоко', 'tags': 'зеленый, красный, вкусный, няшный'}, instance=apple)
    #     f.save()
    #     apple = self.food_model.objects.get(name='яблоко')
    #     self.assert_tags_equal(apple.tags.all(), ['зеленый', 'красный', 'вкусный', 'няшный'])
    #     self.assertEqual(self.food_model.objects.count(), 1)
    #
    #     f = self.form_class({"name": "малина"})
    #     self.assertFalse(f.is_valid())
    #
    #     f = self.form_class(instance=apple)
    #     self.assert_form_renders(f, """<tr><th><label for="id_name">Name:</label></th><td><input id="id_name" type="text" name="name" value="яблоко" maxlength="50" /></td></tr><tr><th><label for="id_tags">Tags:</label></th><td><input type="text" name="tags" value="няшный, зеленый, красный, вкусный" id="id_tags" /><br />%(help_start)sA comma-separated list of tags.%(help_stop)s</td></tr>""")
    #
    #     apple.tags.add('с,запятой')
    #     f = self.form_class(instance=apple)
    #     self.assert_form_renders(f, """<tr><th><label for="id_name">Name:</label></th><td><input id="id_name" type="text" name="name" value="яблоко" maxlength="50" /></td></tr><tr><th><label for="id_tags">Tags:</label></th><td><input type="text" name="tags" value="&quot;с,запятой&quot;, няшный, зеленый, красный, вкусный" id="id_tags" /><br />%(help_start)sA comma-separated list of tags.%(help_stop)s</td></tr>""")
    #
    #     apple.tags.add('с пробелом')
    #     f = self.form_class(instance=apple)
    #     self.assert_form_renders(f, """<tr><th><label for="id_name">Name:</label></th><td><input id="id_name" type="text" name="name" value="яблоко" maxlength="50" /></td></tr><tr><th><label for="id_tags">Tags:</label></th><td><input type="text" name="tags" value="&quot;с пробелом&quot;, &quot;has,comma&quot;, няшный, зеленый, красный, вкусный" id="id_tags" /><br />%(help_start)sA comma-separated list of tags.%(help_stop)s</td></tr>""")

    def test_formfield(self):
        tm = TaggableManager(verbose_name='categories', help_text='Add some categories', blank=True)
        ff = tm.formfield()
        self.assertEqual(ff.label, 'Categories')
        self.assertEqual(ff.help_text, 'Add some categories')
        self.assertEqual(ff.required, False)

        self.assertEqual(ff.clean(""), [])

        tm = TaggableManager()
        ff = tm.formfield()
        self.assertRaises(ValidationError, ff.clean, "")

class TaggableFormDirectTestCase(TaggableFormTestCase):
    form_class = DirectFoodForm
    food_model = DirectFood

class TaggableFormCustomPKTestCase(TaggableFormTestCase):
    form_class = CustomPKFoodForm
    food_model = CustomPKFood

class TaggableFormOfficialTestCase(TaggableFormTestCase):
    form_class = OfficialFoodForm
    food_model = OfficialFood


class TagStringParseTestCase(UnitTestCase):
    """
    Ported from Jonathan Buchanan's `django-tagging
    <http://django-tagging.googlecode.com/>`_
    """

    def test_with_simple_space_delimited_tags(self):
        """
        Test with simple space-delimited tags.
        """
        self.assertEqual(parse_tags('один'), ['один'])
        self.assertEqual(parse_tags('один два'), ['два', 'один' ])
        self.assertEqual(parse_tags('один два три'), ['два', 'один', 'три'])
        self.assertEqual(parse_tags('один один два два'), ['два', 'один'])

    def test_with_comma_delimited_multiple_words(self):
        """
        Test with comma-delimited multiple words.
        An unquoted comma in the input will trigger this.
        """
        self.assertEqual(parse_tags(',один'), ['один'])
        self.assertEqual(parse_tags(',один два'), ['один два'])
        self.assertEqual(parse_tags(',один два три'), ['один два три'])
        self.assertEqual(parse_tags('и-один, и-два и и-три'),
            ['и-два и и-три', 'и-один'])

    def test_with_double_quoted_multiple_words(self):
        """
        Test with double-quoted multiple words.
        A completed quote will trigger this.  Unclosed quotes are ignored.
        """
        self.assertEqual(parse_tags('"один'), ['один'])
        self.assertEqual(parse_tags('"один два'), ['два', 'один'])
        self.assertEqual(parse_tags('"один два три'), ['два', 'один', 'три'])
        self.assertEqual(parse_tags('"один два"'), ['один два'])
        self.assertEqual(parse_tags('и-один "и-два и и-три"'),
            ['и-два и и-три', 'и-один' ])

    def test_with_no_loose_commas(self):
        """
        Test with no loose commas -- split on spaces.
        """
        self.assertEqual(parse_tags('один два "тр,и"'), ['два', 'один', 'тр,и'])

    def test_with_loose_commas(self):
        """
        Loose commas - split on commas
        """
        self.assertEqual(parse_tags('"один", два три'), ['два три', 'один'])

    def test_tags_with_double_quotes_can_contain_commas(self):
        """
        Double quotes can contain commas
        """
        self.assertEqual(parse_tags('и-один "и-два, и и-три"'),
            ['и-два, и и-три', 'и-один'])
        self.assertEqual(parse_tags('"два", один, один, два, "один"'),
            ['два', 'один' ])

    def test_with_naughty_input(self):
        """
        Test with naughty input.
        """
        # Bad users! Naughty users!
        self.assertEqual(parse_tags(None), [])
        self.assertEqual(parse_tags(''), [])
        self.assertEqual(parse_tags('"'), [])
        self.assertEqual(parse_tags('""'), [])
        self.assertEqual(parse_tags('"' * 7), [])
        self.assertEqual(parse_tags(',,,,,,'), [])
        self.assertEqual(parse_tags('",",",",",",","'), [','])
        self.assertEqual(parse_tags('и-один "и-два" и "и-три'),
            ['и', 'и-два', 'и-один', 'и-три' ])

    def test_recreation_of_tag_list_string_representations(self):
        plain = Tag.objects.create(name='просто')
        spaces = Tag.objects.create(name='про белы')
        comma = Tag.objects.create(name='запя,тые')
        self.assertEqual(edit_string_for_tags([plain]), 'просто')
        self.assertEqual(edit_string_for_tags([plain, spaces]), '"про белы", просто')
        self.assertEqual(edit_string_for_tags([plain, spaces, comma]), '"запя,тые", "про белы", просто')
        self.assertEqual(edit_string_for_tags([plain, comma]), '"запя,тые", просто')
        self.assertEqual(edit_string_for_tags([comma, spaces]), '"запя,тые", "про белы"')


@skipIf(django.VERSION < (1, 7), "not relevant for Django < 1.7")
class DeconstructTestCase(UnitTestCase):
    def test_deconstruct_kwargs_kept(self):
        instance = TaggableManager(through=OfficialThroughModel)
        name, path, args, kwargs = instance.deconstruct()
        new_instance = TaggableManager(*args, **kwargs)
        self.assertEqual(instance.rel.through, new_instance.rel.through)


@skipUnless(django.VERSION < (1, 7), "test only applies to 1.6 and below")
class SouthSupportTests(TestCase):
    def test_import_migrations_module(self):
        try:
            from taggit.migrations import __doc__  # noqa
        except ImproperlyConfigured as e:
            exception = e
        self.assertIn("SOUTH_MIGRATION_MODULES", exception.args[0])

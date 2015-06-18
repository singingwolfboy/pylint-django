"""Models."""
from astroid import Const
from astroid.nodes import Assign, Function, AssName, Class
from pylint.interfaces import IAstroidChecker
from pylint.checkers.utils import check_messages
from pylint.checkers import BaseChecker
from pylint_django.__pkginfo__ import BASE_ID
from pylint_django.utils import node_is_subclass, PY3, iter_cls_and_bases


REPR_NAME = '__str__' if PY3 else '__unicode__'

MESSAGES = {
    'E%d01' % BASE_ID: ("%s on a model must be callable (%%s)" % REPR_NAME,
                        'model-unicode-not-callable',
                        "Django models require a callable %s method" % REPR_NAME),
    'W%d01' % BASE_ID: ("No %s method on model (%%s)" % REPR_NAME,
                        'model-missing-unicode',
                        "Django models should implement a %s "
                        "method for string representation" % REPR_NAME),
    'W%d02' % BASE_ID: ("Found __unicode__ method on model (%s). Python3 uses __str__.",
                        'model-has-unicode',
                        "Django models should not implement a __unicode__ "
                        "method for string representation when using Python3"),
    'W%d03' % BASE_ID: ("Model does not explicitly define %s (%%s)" % REPR_NAME,
                        'model-no-explicit-unicode',
                        "Django models should implement a %s method for string representation. "
                        "A parent class of this model does, but ideally all models should be "
                        "explicit." % REPR_NAME)
}


def _is_meta_with_abstract(node):
    if isinstance(node, Class) and node.name == 'Meta':
        for meta_child in node.get_children():
            if not isinstance(meta_child, Assign):
                continue
            if not meta_child.targets[0].name == 'abstract':
                continue
            if not isinstance(meta_child.value, Const):
                continue
                # TODO: handle tuple assignment?
            # eg:
            #    abstract, something_else = True, 1
            if meta_child.value.value:
                # this class is abstract
                return True
    return False


class ModelChecker(BaseChecker):
    """Django model checker."""
    __implements__ = IAstroidChecker

    name = 'django-model-checker'
    msgs = MESSAGES

    @check_messages('model-missing-unicode')
    def visit_class(self, node):
        """Class visitor."""

        if not node_is_subclass(node, 'django.db.models.base.Model'):
            # we only care about models
            return

        has_py2_compat_decorator = False
        for cur_node in iter_cls_and_bases(node):
            if cur_node.qname() == 'django.db.models.base.Model':
                break
            if cur_node.decorators is not None:
                for decorator in cur_node.decorators.nodes:
                    print decorator
                    if getattr(decorator, 'name', None) == 'python_2_unicode_compatible':
                        has_py2_compat_decorator = True
                        break

        for child in node.get_children():
            if _is_meta_with_abstract(child):
                return

            if isinstance(child, Assign):
                grandchildren = list(child.get_children())

                if not isinstance(grandchildren[0], AssName):
                    continue

                name = grandchildren[0].name
                if name != REPR_NAME:
                    continue

                assigned = grandchildren[1].infered()[0]
                if assigned.callable():
                    return

                self.add_message('E%s01' % BASE_ID, args=node.name, node=node)
                return

            if isinstance(child, Function) and child.name == REPR_NAME:
                if PY3 and not has_py2_compat_decorator:
                    self.add_message('W%s02' % BASE_ID, args=node.name, node=node)
                return

        # a different warning is emitted if a parent declares __unicode__
        for method in node.methods():
            if method.name == REPR_NAME:
                # this happens if a parent declares the unicode method but
                # this node does not
                self.add_message('W%s03' % BASE_ID, args=node.name, node=node)
                return

        # if the Django compatibility decorator is used then we don't emit a warning
        # see https://github.com/landscapeio/pylint-django/issues/10
        if not has_py2_compat_decorator:
            self.add_message('W%s01' % BASE_ID, args=node.name, node=node)

# -*- coding: utf-8 -*-

from kobo.types import Enum, EnumItem
from kobo.django.fields import JSONField

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
import django.db.models as models

from service import get_first_result


DEFECT_STATES = Enum(
    # newly introduced defect    
    EnumItem("NEW", help_text="Newly introduced defect"),
    # this one was present in base scan -- nothing new
    EnumItem("OLD", help_text="Defect present in base and this scan."),
    # present in base, but no longer in actual version; good job
    EnumItem("FIXED", help_text="Defect fixed by this build."),
    EnumItem("UNKNOWN", help_text="Default value."),
)

WAIVER_TYPES = Enum(
    # defect is not a bug
    EnumItem("NOT_A_BUG", help_text="Not a bug"),
    # defect is a bug and I'm going to fix it
    EnumItem("IS_A_BUG", help_text="Is a bug"),
    # defect is a bug and I'm going to fix it in next version
    EnumItem("FIX_LATER", help_text="Fix later"),
)

RESULT_GROUP_STATES = Enum(
    # there are some new defects found which need to be reviewed
    EnumItem("NEEDS_INSPECTION", help_text="Needs inspection"),
    # newly added bugs are rewieved and waived
    EnumItem("WAIVED", help_text="Is a bug"),
    # there are no new defects, only fixed one, developer might
    # want to see those
    EnumItem("INFO", help_text="Fix later"),
    # there are no defects associated with this checker group
    EnumItem("PASSED", help_text="Fix later"),
    # this is default state and should be changed ASAP
    EnumItem("UNKNOWN", help_text="Unknown state"),
    # this rg was waived in one of the previous runs
    EnumItem("PREVIOUSLY_WAIVED", help_text="Waived in one of previous runs"),
)


class Result(models.Model):
    """
    Result of submited scan is held by this method.
    """
    scanner = models.CharField("Analyser", max_length=32,
                               blank=True, null=True)
    scanner_version = models.CharField("Analyser's Version",
                                       max_length=32, blank=True, null=True)
    lines = models.IntegerField(help_text='Lines of code scanned', blank=True,
                                null=True)
    #time in seconds that scanner spent scanning
    scanning_time = models.IntegerField(verbose_name='Time spent scanning',
                                        blank=True, null=True)
    date_submitted = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = "date_submitted"

    def new_defects_count(self):
        rgs = ResultGroup.objects.filter(result=self)
        count = 0
        for rg in rgs:
            count += rg.new_defects
        return count

    def fixed_defects_count(self):
        rgs = ResultGroup.objects.filter(result=self)
        count = 0
        for rg in rgs:
            count += rg.fixed_defects
        return count

    def __unicode__(self):
        return "#%d %s %s" % (self.id, self.scanner, self.scanner_version)


class Defect(models.Model):
    """
    One Result is composed of several Defects, each Defect is defined by
    some Events where one is key event
    """
    #ARRAY_VS_SINGLETON | BUFFER_SIZE_WARNING
    checker = models.ForeignKey("Checker", verbose_name="Checker",
                                blank=False, null=False)

    order = models.IntegerField(null=True,
                                help_text="Defects in view have fixed order.")

    #CWE-xxx
    annotation = models.CharField("Annotation", max_length=32,
                                  blank=True, null=True)
    key_event = models.IntegerField(verbose_name="Key event",
                                    help_text="Event that resulted in defect")
    function = models.CharField("Function", max_length=128,
                                help_text="Name of function that contains \
current defect",
                                blank=True, null=True)
    defect_identifier = models.CharField("Defect Identifier", max_length=16,
                                         blank=True, null=True)
    state = models.PositiveIntegerField(default=DEFECT_STATES["UNKNOWN"],
                                        choices=DEFECT_STATES.get_mapping(),
                                        help_text="Defect state")
    result_group = models.ForeignKey('ResultGroup', blank=False, null=False)

    events = JSONField(default=[],
                       help_text="List of defect related events.")

    def __unicode__(self):
        return "#%d Checker: (%s)" % (self.id, self.checker)


class CheckerGroup(models.Model):
    """
    We don't want users to waive each defect so instead we compose checkers
    into specified groups and users waive these groups.
    """
    name = models.CharField("Checker's name", max_length=32,
                            blank=False, null=False)
    enabled = models.BooleanField(default=True, help_text="User may waive \
only ResultGroups which belong to enabled CheckerGroups")

    def __unicode__(self):
        return "#%d %s" % (self.id, self.name)


class ResultGroup(models.Model):
    """
    Each set of defects from existed Result that belongs to some CheckGroup is
    represented by this model
    """
    result = models.ForeignKey(Result, verbose_name="Result",
                               help_text="Result of scan")
    state = models.PositiveIntegerField(
        default=RESULT_GROUP_STATES["UNKNOWN"],
        choices=RESULT_GROUP_STATES.get_mapping(),
        help_text="Type of waiver")
    checker_group = models.ForeignKey(CheckerGroup,
                                      verbose_name="Group of checkers")
    defect_type = models.PositiveIntegerField(
        default=DEFECT_STATES["UNKNOWN"],
        choices=DEFECT_STATES.get_mapping(),
        help_text="Type of defects that are associated with this group.")
    new_defects = models.PositiveSmallIntegerField(
        default=0, blank=True, null=True, verbose_name="New defects count")
    fixed_defects = models.PositiveSmallIntegerField(
        default=0, blank=True, null=True, verbose_name="Fixed defects count")

    def get_first_result_group(self, state):
        """
        Return result group for same checker group, which is associated with
         previous scan (previous build of specified package)
        """
        first_scan = self.result.scanbinding.scan.get_first_scan()
        if first_scan:
            first_result = get_first_result(first_scan)
            if first_result:
                try:
                    return ResultGroup.objects.get(
                        checker_group=self.checker_group,
                        result=first_result,
                        defect_type = DEFECT_STATES[state],
                    )
                except ObjectDoesNotExist:
                    return None

    def is_previously_waived(self):
        return self.state == RESULT_GROUP_STATES['PREVIOUSLY_WAIVED']

    def get_new_defects(self):
        return Defect.objects.filter(result_group=self.id,
                                     state=DEFECT_STATES['NEW'])

    def get_defects_diff(self, state):
        """
        diff between number of new defects from this scan and first
         return None, if previous scan does not exist

        @rtype: None or int
        @return:
            -1: one new defect fixed
            +2: there are two newly added defects
        """
        prev_rg = self.get_first_result_group(state)

        if prev_rg is None:
            if self.result.scanbinding.scan.get_child_scan():
                if state == 'NEW':
                    return self.new_defects
                elif state == 'FIXED':
                    return self.fixed_defects
            else:
                return None
        else:
            if state == 'NEW':
                return self.new_defects - prev_rg.new_defects
            elif state == 'FIXED':
                return self.fixed_defects - prev_rg.fixed_defects

    def get_defects_diff_display(self, state, response):
        defects_diff = self.get_defects_diff(state)
        if defects_diff:  # not None & != 0
            diff_html = '<span class="%s">%s%d</span>'
            if state == 'NEW':
                if defects_diff > 0:
                    response += diff_html % ('defects_increased', '+',
                                             defects_diff)
                elif defects_diff < 0:
                    response += diff_html % ('defects_decreased', '-',
                                             defects_diff)
            elif state == 'FIXED':
                if defects_diff > 0:
                    response += diff_html % ('defects_decreased', '+',
                                             defects_diff)
                elif defects_diff < 0:
                    response += diff_html % ('defects_increased', '-',
                                             defects_diff)
        return response

    def get_state_to_display(self, state, defects_count):
        """
        return state for CSS class
        """
        if state == 'FIXED':
            if defects_count > 0:
                return 'INFO'
            else:
                return 'PASSED'
        elif state == "NEW":
            if defects_count > 0:
                return self.get_state_display()
            else:
                return 'PASSED'

    def display_in_result(self, state, url_name):
        """
        return HTML formatted representation of result group displayed in
         waiver, if there are some defects related to this group, create link
         and display number of defects
        @param state: 'NEW' | 'FIXED'
        """
        defects = Defect.objects.filter(result_group=self.id,
                                        state=DEFECT_STATES[state])
        group_state = self.get_state_to_display(state, len(defects))
        checker_group = self.checker_group.name
        response = '<td class="%s">' % group_state
        if defects.count() > 0:
            url = reverse(url_name, args=(self.result.id, self.id))
            response += '<a href="%s#defects">' % url
        response += checker_group
        if defects.count() > 0:
            response += '</a> <span class="%s">%s</span>' % (state,
                                                             defects.count())
        response = self.get_defects_diff_display(state, response)
        response += '</td>'
        return response

    def __unicode__(self):
        return "#%d [%s - %s], Result: (%s)" % (
            self.id, self.checker_group.name, self.get_state_display(),
            self.result
        )


class Checker(models.Model):
    """
    Checker is a type of defect.
    """
    name = models.CharField("Checker's name", max_length=32,
                            blank=False, null=False)
    # if you use get_or_create, it will save it
    group = models.ForeignKey(CheckerGroup, verbose_name="Checker group",
                              blank=True, null=True,
                              help_text="Name of group where does this \
checker belong")

    def __unicode__(self):
        return "#%d %s, CheckerGroup: (%s)" % (self.id, self.name, self.group)


class Waiver(models.Model):
    """
    User acknowledges that he processed this defect
    """
    date = models.DateTimeField()  # date submitted
    message = models.TextField("Message")
    result_group = models.ForeignKey(ResultGroup, blank=False, null=False,
                                     help_text="Group of defects which is \
waived for specific Result")
    user = models.ForeignKey(User)
    state = models.PositiveIntegerField(default=WAIVER_TYPES["IS_A_BUG"],
                                        choices=WAIVER_TYPES.get_mapping(),
                                        help_text="Type of waiver")

    class Meta:
        get_latest_by = "date"

    def __unicode__(self):
        return "#%d %s - %s, ResultGroup: (%s)" % (self.id, self.message,
                                                   self.get_state_display(),
                                                   self.result_group)
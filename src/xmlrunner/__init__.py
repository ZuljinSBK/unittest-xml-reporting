# -*- coding: utf-8 -*-

"""
This module provides the XMLTestRunner class, which is heavily based on the
default TextTestRunner.
"""

import os
import re
import sys
import time
try:
    from unittest2.runner import TextTestRunner
    from unittest2.runner import TextTestResult as _TextTestResult
    from unittest2.result import TestResult
except ImportError:
    from unittest import TestResult, _TextTestResult, TextTestRunner

try:
    # Removed in Python 3
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

# Allow version to be detected at runtime.
from .version import __version__, __version_info__
from collections import OrderedDict

try:
    # Python 3 has a bytes type and in Python 2.6+ bytes is an alias to str.
    bytestring_type = bytes
except NameError:
    bytestring_type = str

class _DelegateIO(object):
    """
    This class defines an object that captures whatever is written to
    a stream or file.
    """

    def __init__(self, delegate):
        self._captured = StringIO()
        self.delegate = delegate

    def write(self, text):
        self._captured.write(text)
        self.delegate.write(text)

    def reset(self):
        self._captured.truncate(0)
        self._captured.seek(0)

    def __getattr__(self, attr):
        return getattr(self._captured, attr)

# Matches invalid XML1.0 unicode characters, like control characters:
# http://www.w3.org/TR/2006/REC-xml-20060816/#charsets
INVALID_XML_1_0_UNICODE_RE = re.compile(
    u'[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]', re.UNICODE)


def xml_safe_unicode(base, encoding='utf-8'):
    """Return a unicode string containing only valid XML characters.

    encoding - if base is a byte string it is first decoded to unicode
        using this encoding.
    """
    if isinstance(base, bytestring_type):
        base = base.decode(encoding)
    return INVALID_XML_1_0_UNICODE_RE.sub('', base)

def testcase_name(test_method):
    testcase = type(test_method)

    # Ignore module name if it is '__main__'
    module = testcase.__module__ + '.'
    if module == '__main__.':
        module = ''
    result = module + testcase.__name__
    return result


class _TestInfo(object):
    """
    This class keeps useful information about the execution of a
    test method.
    """

    # Possible test outcomes
    (SUCCESS, FAILURE, ERROR, SKIP) = range(4)

    def __init__(self, test_result, test_method, outcome=SUCCESS, err=None,
                 std_output=None, err_output=None):
        self.test_result = test_result
        self.test_method = test_method
        self.outcome = outcome
        self.test_index = 0
        self.elapsed_time = 0
        self.err = err
        self.std_output = std_output
        self.err_output = err_output

        self.test_description = self.test_result.getDescription(test_method)
        self.test_exception_info = (
            '' if outcome in (self.SUCCESS, self.SKIP)
            else self.test_result._exc_info_to_string(
                    self.err, test_method)
        )

        self.test_name = testcase_name(test_method)
        self.test_id = test_method.id()

    def id(self):
        return self.test_method.id()

    def test_finished(self):
        """Save info that can only be calculated once a test has run.
        """
        self.test_index = self.test_result.test_index
        self.elapsed_time = \
            self.test_result.stop_time - self.test_result.start_time

    def get_description(self):
        """
        Return a text representation of the test method.
        """
        return self.test_description

    def get_error_info(self):
        """
        Return a text representation of an exception thrown by a test
        method.
        """
        return self.test_exception_info

    def get_std_output(self):
        """
        Return a text representation of standard output caught during test.
        """
        return self.std_output

    def get_err_output(self):
        """
        Return a text representation of standard error output caught during test.
        """
        return self.err_output


class _XMLTestResult(_TextTestResult):
    """
    A test result class that can express test results in a XML report.

    Used by XMLTestRunner.
    """
    def __init__(self, stream=sys.stderr, descriptions=1, verbosity=1,
                 elapsed_times=True, per_test_output=False, encoding='utf-8'):
        _TextTestResult.__init__(self, stream, descriptions, verbosity)
        self.successes = []
        self.callback = None
        self.elapsed_times = elapsed_times
        self.per_test_output = per_test_output
        self.encoding = encoding
        self.test_index = 0

    def _prepare_callback(self, test_info, target_list, verbose_str,
                          short_str):
        """
        Appends a _TestInfo to the given target list and sets a callback
        method to be called by stopTest method.
        """
        target_list.append(test_info)

        def callback():
            """Prints the test method outcome to the stream, as well as
            the elapsed time.
            """

            test_info.test_finished()

            # Ignore the elapsed times for a more reliable unit testing
            if not self.elapsed_times:
                self.start_time = self.stop_time = 0

            if self.showAll:
                self.stream.writeln(
                    '%s (%.3fs)' % (verbose_str, test_info.elapsed_time)
                )
            elif self.dots:
                self.stream.write(short_str)
        self.callback = callback

    def startTest(self, test):
        """
        Called before execute each test method.
        """
        self.start_time = time.time()
        TestResult.startTest(self, test)

        if self.showAll:
            self.stream.write('  ' + self.getDescription(test))
            self.stream.write(" ... ")

    def stopTest(self, test):
        """
        Called after execute each test method.
        """
        _TextTestResult.stopTest(self, test)
        self.stop_time = time.time()

        if self.callback and callable(self.callback):
            self.callback()
            self.callback = None

        self.test_index += 1

    def addSuccess(self, test):
        """
        Called when a test executes successfully.
        """
        if self.per_test_output:
            testinfo = _TestInfo(self, test, 
                                 std_output=sys.stdout.getvalue(), err_output=sys.stderr.getvalue())
            sys.stdout.reset()
            sys.stderr.reset()
        else:
            testinfo = _TestInfo(self, test)
        self._prepare_callback(
            testinfo, self.successes, 'OK', '.'
        )

    def addFailure(self, test, err):
        """
        Called when a test method fails.
        """
        if self.per_test_output:
            testinfo = _TestInfo(self, test, _TestInfo.ERROR, err,
                                 std_output=sys.stdout.getvalue(), err_output=sys.stderr.getvalue())
            sys.stdout.reset()
            sys.stderr.reset()
        else:
            testinfo = _TestInfo(self, test, _TestInfo.ERROR, err)
        self.errors.append((
            testinfo,
            self._exc_info_to_string(err, test)
        ))
        self._prepare_callback(testinfo, [], 'FAIL', 'F')

    def addError(self, test, err):
        """
        Called when a test method raises an error.
        """
        if self.per_test_output:
            testinfo = _TestInfo(self, test, _TestInfo.ERROR, err,
                                 std_output=sys.stdout.getvalue(), err_output=sys.stderr.getvalue())
            sys.stdout.reset()
            sys.stderr.reset()
        else:
            testinfo = _TestInfo(self, test, _TestInfo.ERROR, err)
        self.errors.append((
            testinfo,
            self._exc_info_to_string(err, test)
        ))
        self._prepare_callback(testinfo, [], 'ERROR', 'E')

    def addSkip(self, test, reason):
        """
        Called when a test method was skipped.
        """
        if self.per_test_output:
            testinfo = _TestInfo(self, test, _TestInfo.SKIP, reason,
                                 std_output=sys.stdout.getvalue(), err_output=sys.stderr.getvalue())
            sys.stdout.reset()
            sys.stderr.reset()
        else:
            testinfo = _TestInfo(self, test, _TestInfo.SKIP, reason)
        self.skipped.append((testinfo, reason))
        self._prepare_callback(testinfo, [], 'SKIP', 'S')

    def printErrorList(self, flavour, errors):
        """
        Writes information about the FAIL or ERROR to the stream.
        """
        for test_info, error in errors:
            self.stream.writeln(self.separator1)
            self.stream.writeln(
                '%s [%.3fs]: %s' % (flavour, test_info.elapsed_time,
                                    test_info.get_description())
            )
            self.stream.writeln(self.separator2)
            self.stream.writeln('%s' % test_info.get_error_info())

    def _get_info_by_testcase(self, outsuffix):
        """
        Organizes test results by TestCase module. This information is
        used during the report generation, where a XML report will be created
        for each TestCase.
        """
        testcase_list = []
        tests_by_testcase = OrderedDict()

        for tests in (self.successes, self.failures, self.errors, self.skipped):
            for test_info in tests:
                if isinstance(test_info, tuple):
                    # This is a skipped, error or a failure test case
                    test_info = test_info[0]
                testcase_name = test_info.test_name
                testcase_list.append((testcase_name, test_info))
        testcase_list.sort(key=lambda x: x[1].test_index)

        for test in testcase_list:
            if not test[0] in tests_by_testcase:
                tests_by_testcase[test[0]] = []
            tests_by_testcase[test[0]].append(test[1])

        return tests_by_testcase

    def _report_testsuite(suite_name, outsuffix, tests, xml_node, xml_document):
        """
        Appends the testsuite section to the XML document.
        """
        testsuite = xml_document.createElement('testsuite')
        xml_node.appendChild(testsuite)

        testsuite.setAttribute('name', "%s-%s" % (suite_name, outsuffix))
        testsuite.setAttribute('tests', str(len(tests)))

        testsuite.setAttribute(
            'time', '%.3f' % sum(map(lambda e: e.elapsed_time, tests))
        )
        failures = filter(lambda e: e.outcome == _TestInfo.FAILURE, tests)
        testsuite.setAttribute('failures', str(len(list(failures))))

        errors = filter(lambda e: e.outcome == _TestInfo.ERROR, tests)
        testsuite.setAttribute('errors', str(len(list(errors))))

        return testsuite

    _report_testsuite = staticmethod(_report_testsuite)

    def _test_method_name(test_id):
        """
        Returns the test method name.
        """
        return test_id.split('.')[-1]

    _test_method_name = staticmethod(_test_method_name)

    def _report_testcase(suite_name, test_result, xml_testsuite, xml_document,
                         encoding='utf-8'):
        """
        Appends a testcase section to the XML document.
        """
        testcase = xml_document.createElement('testcase')
        xml_testsuite.appendChild(testcase)

        testcase.setAttribute('classname', suite_name)
        testcase.setAttribute(
            'name', _XMLTestResult._test_method_name(test_result.test_id)
        )
        testcase.setAttribute('time', '%.3f' % test_result.elapsed_time)

        if (test_result.outcome != _TestInfo.SUCCESS):
            elem_name = ('failure', 'error', 'skipped')[test_result.outcome - 1]
            failure = xml_document.createElement(elem_name)
            testcase.appendChild(failure)
            if test_result.outcome != _TestInfo.SKIP:
                failure.setAttribute('type', test_result.err[0].__name__)
                failure.setAttribute('message', xml_safe_unicode(str(test_result.err[1]), encoding))
                error_info = xml_safe_unicode(test_result.get_error_info(), encoding)
                failureText = xml_document.createCDATASection(error_info)
                failure.appendChild(failureText)
            else:
                failure.setAttribute('type', 'skip')
                failure.setAttribute('message', xml_safe_unicode(test_result.err, encoding))

        if test_result.get_std_output():
            systemout = xml_document.createElement('system-out')
            testcase.appendChild(systemout)
            systemout_text = xml_document.createCDATASection(xml_safe_unicode(test_result.get_std_output(), encoding))
            systemout.appendChild(systemout_text)
        if test_result.get_err_output():
            systemerr = xml_document.createElement('system-err')
            testcase.appendChild(systemerr)
            systemerr_text = xml_document.createCDATASection(xml_safe_unicode(test_result.get_err_output(), encoding))
            systemerr.appendChild(systemerr_text)

    _report_testcase = staticmethod(_report_testcase)

    def _report_output(test_runner, xml_testsuite, xml_document,
                       encoding='utf-8'):
        """
        Appends the system-out and system-err sections to the XML document.
        """
        systemout = xml_document.createElement('system-out')
        xml_testsuite.appendChild(systemout)

        systemout_text = xml_document.createCDATASection(xml_safe_unicode(sys.stdout.getvalue(), encoding))
        systemout.appendChild(systemout_text)

        systemerr = xml_document.createElement('system-err')
        xml_testsuite.appendChild(systemerr)

        systemerr_text = xml_document.createCDATASection(xml_safe_unicode(sys.stderr.getvalue(), encoding))
        systemerr.appendChild(systemerr_text)

    _report_output = staticmethod(_report_output)
    
    def _add_xml_report(self, test_runner, suite, tests, node, doc):
            # Build the XML file
            testsuite = _XMLTestResult._report_testsuite(
                suite, test_runner.outsuffix, tests, node, doc
            )
            for test in tests:
                _XMLTestResult._report_testcase(suite, test, testsuite, doc, encoding=self.encoding)
            if not self.per_test_output:
                _XMLTestResult._report_output(test_runner, testsuite, doc, encoding=self.encoding)
            xml_content = doc.toprettyxml(indent='\t', encoding=self.encoding)
            return xml_content

    def generate_reports(self, test_runner):
        """
        Generates the XML reports to a given XMLTestRunner object.
        """
        from xml.dom.minidom import Document
        all_results = self._get_info_by_testcase(test_runner.outsuffix)

        if isinstance(test_runner.output, str) and not test_runner.output.lower().endswith(".xml"):
            if not os.path.exists(test_runner.output):
                os.makedirs(test_runner.output)
            for suite, tests in all_results.items():
                doc = Document()
                self._add_xml_report(test_runner, suite, tests, doc, doc)
                xml_content = doc.toprettyxml(indent='\t', encoding=self.encoding)
                if test_runner.outsuffix:
                    filename = '%s%sTEST-%s-%s.xml' % (test_runner.output, os.sep, suite, test_runner.outsuffix)
                else:
                    filename = '%s%sTEST-%s.xml' % (test_runner.output, os.sep, suite)
                with open(filename, 'wb') as report_file:
                    report_file.write(xml_content)

        elif isinstance(test_runner.output, str) and test_runner.output.lower().endswith(".xml"):
            file, ext = os.path.splitext(os.path.abspath(test_runner.output))
            dir, base = os.path.split(os.path.abspath(test_runner.output))
            if not os.path.exists(dir):
                os.makedirs(dir)

            doc = Document()
            xml_suites = doc.createElement('testsuites')
            doc.appendChild(xml_suites)
            if test_runner.outsuffix:
                filename = '%s-%s%s' % (file, test_runner.outsuffix, ext)
            else:
                filename = '%s%s' % (file, ext)
            with open(filename, 'wb') as report_file:
                for suite, tests in all_results.items():
                    self._add_xml_report(test_runner, suite, tests, xml_suites, doc)
                xml_content = doc.toprettyxml(indent='\t', encoding=self.encoding)
                report_file.write(xml_content)
        else:
            for suite, tests in all_results.items():
                # Assume that test_runner.output is a stream
                doc = Document()
                self._add_xml_report(test_runner, suite, tests, doc, doc)
                xml_content = doc.toprettyxml(indent='\t', encoding=self.encoding)
                test_runner.output.write(xml_content)


class XMLTestRunner(TextTestRunner):
    """
    A test runner class that outputs the results in JUnit like XML files.
    """
    def __init__(self, output='.', outsuffix=None, stream=sys.stderr,
                 descriptions=True, verbosity=1, elapsed_times=True,
                 per_test_output=False, encoding='utf-8'):
        TextTestRunner.__init__(self, stream, descriptions, verbosity)
        self.verbosity = verbosity
        self.output = output
        if outsuffix:
            self.outsuffix = outsuffix
        else:
            self.outsuffix = time.strftime("%Y%m%d%H%M%S")
        self.elapsed_times = elapsed_times
        self.per_test_output = per_test_output
        self.encoding = encoding

    def _make_result(self):
        """
        Creates a TestResult object which will be used to store
        information about the executed tests.
        """
        return _XMLTestResult(
            self.stream, self.descriptions, self.verbosity, self.elapsed_times, self.per_test_output, self.encoding
        )

    def _patch_standard_output(self):
        """
        Replaces stdout and stderr streams with string-based streams
        in order to capture the tests' output.
        """
        sys.stdout = _DelegateIO(sys.stdout)
        sys.stderr = _DelegateIO(sys.stderr)

    def _restore_standard_output(self):
        """
        Restores stdout and stderr streams.
        """
        sys.stdout = sys.stdout.delegate
        sys.stderr = sys.stderr.delegate

    def run(self, test):
        """
        Runs the given test case or test suite.
        """
        try:
            # Prepare the test execution
            self._patch_standard_output()
            result = self._make_result()

            # Print a nice header
            self.stream.writeln()
            self.stream.writeln('Running tests...')
            self.stream.writeln(result.separator2)

            # Execute tests
            start_time = time.time()
            test(result)
            stop_time = time.time()
            time_taken = stop_time - start_time

            # Print results
            result.printErrors()
            self.stream.writeln(result.separator2)
            run = result.testsRun
            self.stream.writeln("Ran %d test%s in %.3fs" % (
                run, run != 1 and "s" or "", time_taken)
            )
            self.stream.writeln()

            expectedFails = unexpectedSuccesses = skipped = 0
            try:
                results = map(len, (result.expectedFailures,
                                    result.unexpectedSuccesses,
                                    result.skipped))
            except AttributeError:
                pass
            else:
                expectedFails, unexpectedSuccesses, skipped = results

            # Error traces
            infos = []
            if not result.wasSuccessful():
                self.stream.write("FAILED")
                failed, errored = map(len, (result.failures, result.errors))
                if failed:
                    infos.append("failures={0}".format(failed))
                if errored:
                    infos.append("errors={0}".format(errored))
            else:
                self.stream.write("OK")

            if skipped:
                infos.append("skipped={0}".format(skipped))
            if expectedFails:
                infos.append("expected failures={0}".format(expectedFails))
            if unexpectedSuccesses:
                infos.append("unexpected successes={0}".format(unexpectedSuccesses))

            if infos:
                self.stream.writeln(" ({0})".format(", ".join(infos)))
            else:
                self.stream.write("\n")

            # Generate reports
            self.stream.writeln()
            self.stream.writeln('Generating XML reports...')
            result.generate_reports(self)
        finally:
            self._restore_standard_output()

        return result

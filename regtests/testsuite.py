#!/usr/bin/env python
#                              Ada Web Server
#
#                          Copyright (C) 2003-2009
#                                  AdaCore
#
#  This library is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or (at
#  your option) any later version.
#
#  This library is distributed in the hope that it will be useful, but
#  WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this library; if not, write to the Free Software Foundation,
#  Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
#  As a special exception, if other files instantiate generics from this
#  unit, or you link this unit with other files to produce an executable,
#  this  unit  does not  by itself cause  the resulting executable to be
#  covered by the GNU General Public License. This exception does not
#  however invalidate any other reasons why the executable file  might be
#  covered by the  GNU Public License.

"""
./testsuite.py [OPTIONS]

This module is the main driver for AWS testsuite
"""
import logging
import os
import shutil
import sys

from glob import glob
from makevar import MakeVar

# Importing gnatpython modules
CURDIR = os.getcwd()
PYTHON_SUPPORT = os.path.join(CURDIR, "python_support")
sys.path.append(PYTHON_SUPPORT)

from gnatpython.ex import Run
from gnatpython.fileutils import ln, cp
from gnatpython.main import Main
from gnatpython.mainloop import MainLoop
from gnatpython.optfileparser import OptFileParse
from gnatpython.report import Report, GenerateRep

DURATION_REPORT_NAME = "testsuite.duration"
TESTSUITE_RES     = "testsuite.res"
TESTSUITE_REP     = "testsuite.rep"
OLD_TESTSUITE_RES = "testsuite.res_last"

OUTPUTS_DIR   = os.path.join(CURDIR, ".outputs")
BUILDS_DIR    = os.path.join(CURDIR, ".build")
DIFFS_DIR     = os.path.join(OUTPUTS_DIR, 'diffs')
PROFILES_DIR  = os.path.join(OUTPUTS_DIR, 'profiles')

BUILD_FAILURE   = 1
DIFF_FAILURE    = 2
UNKNOWN_FAILURE = 3

CONFIG_TEMPLATE = """
import logging
import os
import sys
import test_support

PROFILES_DIR    = r"%(profiles_dir)s"
DIFFS_DIR       = r"%(diffs_dir)s"
WITH_GPROF      = %(with_gprof)s
WITH_GDB        = %(with_gdb)s
WITH_VALGRIND   = %(with_valgrind)s
WITH_GPRBUILD   = %(with_gprbuild)s
BUILD_FAILURE   = %(build_failure)d
DIFF_FAILURE    = %(diff_failure)d
UNKNOWN_FAILURE = %(unknown_failure)d

def set_config():
    # Set python path
    sys.path.append(r"%(python_support)s")

    log_filename = os.path.basename(test_support.TESTDIR) + '.log'

    logging.basicConfig(level=logging.DEBUG,
                        datefmt='%%H:%%M:%%S',
                        filename=os.path.join(r'%(log_dir)s',
                                              log_filename),
                        mode="w")

    console = logging.StreamHandler()
    formatter = logging.Formatter('%%(levelname)-8s %%(message)s')
    console.setFormatter(formatter)
    console.setLevel(logging.%(logging_level)s)
    logging.getLogger('').addHandler(console)
"""

class Runner(object):
    """Run the testsuite

    Build a list of all subdirectories containing test.py then, for
    each test, parse the test.opt file (if exists) and run the test
    (by spawning a python process).
    """

    def __init__(self, options):
        """Fill the test lists"""

        self.config = options
        if self.config.with_gdb:
            # Serialize runs and disable gprof
            self.config.jobs = 1
            self.config.with_gprof = False

        self.config.logging_level = self._logging_level()

        if self.config.tags is None:
            # Read tags from testsuite.tags
            # The file testsuite.tags should have been generated by
            # AWS 'make setup'
            try:
                tags_file = open('testsuite.tags')
                self.config.tags = tags_file.read().strip()
                tags_file.close()
            except IOError:
                print "Cannot find testsuite.tags. Please run make setup"
                sys.exit(1)

        if self.config.from_build_dir:
            os.environ["ADA_PROJECT_PATH"] = CURDIR
            # Read makefile.setup to set proper build environment
            c = MakeVar('../makefile.setup')
            os.environ["PRJ_BUILD"] = c.get(
                "DEBUG", "true", "Debug", "Release")
            os.environ["PRJ_XMLADA"] = c.get(
                "XMLADA", "true", "Installed", "Disabled")
            os.environ["PRJ_ASIS"] = c.get(
                "ASIS", "true", "Installed", "Disabled")
            os.environ["PRJ_LDAP"] = c.get(
                "LDAP", "true", "Installed", "Disabled")
            os.environ["SOCKET"] = c.get("SOCKET")
            os.environ["LIBRARY_TYPE"] = "static"
            # Add current tools in from of PATH
            os.environ["PATH"] = CURDIR + os.sep + ".." + os.sep \
              + ".build" + os.sep + os.environ["PRJ_BUILD"].lower() \
              + os.sep + "static" + os.sep + "tools" \
              + os.pathsep + os.environ["PATH"]

        logging.debug("Running the testsuite with the following tags: %s" %
                      self.config.tags)

        # Open report file
        self.report = Report(TESTSUITE_RES,
                             discs=self.config.tags.replace(',', ', '))

        # Set python path
        if "PYTHONPATH" in os.environ:
            pythonpath = os.environ["PYTHONPATH"]
        else:
            pythonpath = ""
        os.environ["PYTHONPATH"] = CURDIR + os.pathsep + pythonpath

        # generate config.py that will be read by runtest.py
        config_py = open('config.py', 'w')
        config_py_dict = self.config.__dict__
        config_py_dict['python_support']  = PYTHON_SUPPORT
        config_py_dict['profiles_dir']    = PROFILES_DIR
        config_py_dict['diffs_dir']       = DIFFS_DIR
        config_py_dict['build_failure']   = BUILD_FAILURE
        config_py_dict['unknown_failure'] = UNKNOWN_FAILURE
        config_py_dict['diff_failure']    = DIFF_FAILURE
        config_py_dict['log_dir']         = OUTPUTS_DIR

        config_py.write(CONFIG_TEMPLATE % config_py_dict)
        config_py.close()

    def _logging_level(self):
        """Returns the requested logging level"""
        if self.config.verbose:
            return "DEBUG"
        elif self.config.view_diffs:
            return "ERROR"
        else:
            return "CRITICAL"

    def _get_testnames(self):
        """Returns the list of tests to run"""
        tests_list = []
        if self.config.tests is None:
            # Get all test.py
            tests_list = sorted(glob('*/test.py'))
        else:
            # tests parameter can be a file containing a list of tests
            if os.path.isfile(self.config.tests):
                list_file = open(self.config.tests)
                tests_list = []
                for line in list_file:
                    test_name = line.rstrip().split(':')[0]
                    tests_list.append(os.path.join(test_name, 'test.py'))
                list_file.close()
            else:
                # or a space separated string
                tests_list = [os.path.join(t, "test.py")
                        for t in self.config.tests.split()]

        if self.config.with_Z999:
            tests_list.insert(0, os.path.join("Z999_xfail", "always_fail.py"))
        return tests_list

    def report_result(self, name, status, comment="", diff_content=""):
        """Add a test result in testsuite.res file.

        This will also log the result for interactive use of the testsuite.
        """
        self.report.add(name, status,
                        comment=comment.strip('"'), diff=diff_content)

        result = "%-60s %-9s %s" % (name, status, comment)

        test_desc_filename = os.path.join(name, "test.desc")
        if os.path.exists(test_desc_filename):
            test_desc = open(test_desc_filename, 'r')
            result = "%s [%s]" % (result, test_desc.read().strip())
            test_desc.close()
        logging.info(result)

    def start(self):
        """Start the testsuite"""
        linktree("common", os.path.join(BUILDS_DIR, "common"))

        # Generate the testcases list
        # Report all DEAD tests
        testcases = []
        for test_py in self._get_testnames():
            testcase = TestCase(test_py)
            testcase.parseopt(self.config.tags)
            if testcase.is_dead():
                self.report_result(testcase.testdir,
                            "DEAD", testcase.getopt('dead'))
            else:
                testcases.append(testcase)

        # Run the main loop
        collect_result = gen_collect_result(self.report_result)
        MainLoop(testcases, run_testcase, collect_result, self.config.jobs)
        self.report.write()

        old_results = None
        if self.config.old_res and os.path.exists(self.config.old_res):
            old_results = self.config.old_res
        elif os.path.exists(OLD_TESTSUITE_RES):
            old_results = OLD_TESTSUITE_RES

        testsuite_rep = GenerateRep(TESTSUITE_RES, old_results)
        report_file = open(TESTSUITE_REP, 'w')
        report_file.write(testsuite_rep.get_subject())
        report_file.write(testsuite_rep.get_report
                          (additional_header='Tags: ' + self.config.tags))
        report_file.close()

        # Save result in OLD_TESTSUITE_RES for next run
        cp(TESTSUITE_RES, OLD_TESTSUITE_RES)

def linktree(src, dst, symlinks=0):
    """Hard link all files from src directory in dst directory"""
    names = os.listdir(src)
    os.mkdir(dst)
    for name in names:
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if symlinks and os.path.islink(srcname):
                linkto = os.readlink(srcname)
                os.symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                linktree(srcname, dstname, symlinks)
            else:
                ln(srcname, dstname)
        except (IOError, os.error), why:
            print "Can't link %s to %s: %s" % (srcname, dstname, str(why))

def run_testcase(test, _job_info):
    """Run a single test"""
    logging.debug("Running " + test.testdir)
    linktree(test.testdir, os.path.join(BUILDS_DIR, test.testdir))
    timeout = test.getopt('limit')
    if timeout is not None:
        env = os.environ.copy()
        env['TIMEOUT'] = timeout
    else:
        env = None

    return Run([sys.executable,
                os.path.join(BUILDS_DIR, test.filename)],
               bg=True, output=None, error=None, env=env)

def gen_collect_result(report_func):
    """Returns the collect_result function"""
    def collect_result(test, process, _job_info):
        """Collect a test result"""
        xfail = test.getopt('xfail', None)
        diff_content = ""
        # Compute job status
        # The status can be UOK, OK, XFAIL, DIFF or PROBLEM
        if process.status == 0:
            if xfail:
                status = 'UOK'
            else:
                status = 'OK'
        else:
            if xfail is not None:
                status = 'XFAIL'
            elif process.status == DIFF_FAILURE:
                status = 'DIFF'
            else:
                status = 'PROBLEM'
            diff_fname = os.path.join(DIFFS_DIR, test.testdir + '.diff')
            if os.path.exists(diff_fname):
                f = open(diff_fname)
                diff_content = f.read()
                f.close()

        report_func(test.testdir, status, xfail or "", diff_content)
    return collect_result

class TestCase(object):
    """Creates a TestCase object.

    Contains the result of the test.opt parsing
    """
    def __init__(self, filename):
        """Create a new TestCase for the given filename"""
        self.testdir  = os.path.dirname(filename)
        self.filename = filename
        self.opt = None

    def __lt__(self, right):
        """Use filename alphabetical order"""
        return self.filename < right.filename

    def parseopt(self, tags):
        """Parse the test.opt with the given tags"""
        test_opt = os.path.join(self.testdir, 'test.opt')
        if os.path.exists(test_opt):
            self.opt = OptFileParse(tags, test_opt)

    def getopt(self, key, default=None):
        """Get the value extracted from test.opt that correspond to key

        If key is not found. Returns default.
        """
        if self.opt is None:
            return default
        else:
            return self.opt.get_value(key, default_value=default)

    def is_dead(self):
        """Returns True if the test is DEAD"""
        if self.opt is None:
            return False
        else:
            return self.opt.is_dead

def run_testsuite():
    """Main: parse command line and run the testsuite"""

    if os.path.exists(OUTPUTS_DIR):
        shutil.rmtree(OUTPUTS_DIR)
    os.mkdir(OUTPUTS_DIR)
    os.mkdir(os.path.join(OUTPUTS_DIR, 'profiles'))
    os.mkdir(os.path.join(OUTPUTS_DIR, 'diffs'))

    if os.path.exists(BUILDS_DIR):
        shutil.rmtree(BUILDS_DIR)
    os.mkdir(BUILDS_DIR)

    # Add rlimit to PATH
    os.environ["PATH"] = os.environ["PATH"] + os.pathsep + CURDIR

    logging.basicConfig(level=logging.DEBUG,
                        filename='%s/testsuite.log' % OUTPUTS_DIR, mode='w')
    main = Main(formatter='%(message)s')
    main.add_option("--tests", dest="tests",
                    help="list of tests to run, a space separated string or " \
                        "a filename.")
    main.add_option("--with-Z999", dest="with_Z999",
                    action="store_true", default=False,
                    help="Add a test that always fail")
    main.add_option("--view-diffs", dest="view_diffs", action="store_true",
                    default=False, help="show diffs on stdout")
    main.add_option("--delay", dest="delay", type="float", default=0.1,
                    help="Delay between two loops")
    main.add_option("--tags", dest="tags",
                    help="tags to use instead of testsuite.tags content")
    main.add_option("--with-gprof", dest="with_gprof", action="store_true",
                    default=False, help="Generate profiling reports")
    main.add_option("--with-gdb", dest="with_gdb", action="store_true",
                    default=False, help="Run with gdb")
    main.add_option("--with-valgrind", dest="with_valgrind",
                    action="store_true", default=False,
                    help="Run with valgrind")
    main.add_option("--with-gnatmake", dest="with_gprbuild",
                    action="store_false", default=False,
                    help="Compile with gnatmake")
    main.add_option("--with-gprbuild", dest="with_gprbuild",
                    action="store_true", default=False,
                    help="Compile with gprbuild (default is gnatmake)")
    main.add_option("--old-res", dest="old_res", type="string",
                    help="Old testsuite.res file")
    main.add_option("--from-build-dir", dest="from_build_dir",
                    action="store_true", default=False,
                    help="Run testsuite from local build (in repository)")
    main.parse_args()

    run = Runner(main.options)
    run.start()

if __name__ == "__main__":
    # Run the testsuite
    run_testsuite()

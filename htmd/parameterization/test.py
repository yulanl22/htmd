# (c) 2015-2017 Acellera Ltd http://www.acellera.com
# All Rights Reserved
# Distributed under HTMD Software License Agreement
# No redistribution in whole or part
#
import os
import sys
import shutil
import unittest
from subprocess import call

from htmd.home import home
from htmd.util import tempname


def _loadFiles(folder1, folder2):
    import parmed
    from htmd.molecule.molecule import Molecule, mol_equal
    mol1 = Molecule(os.path.join(folder1, 'mol.mol2'))
    mol2 = Molecule(os.path.join(folder2, 'mol.mol2'))
    assert mol_equal(mol1, mol2)

    if os.path.exists(os.path.join(folder1, 'mol.frcmod')) and \
        os.path.exists(os.path.join(folder2, 'mol.frcmod')):
        prm1 = parmed.load_file(os.path.join(folder1, 'mol.frcmod'))
        prm2 = parmed.load_file(os.path.join(folder2, 'mol.frcmod'))
    elif os.path.exists(os.path.join(folder1, 'mol.prm')) and \
        os.path.exists(os.path.join(folder1, 'mol.rtf')) and \
        os.path.exists(os.path.join(folder2, 'mol.prm')) and \
        os.path.exists(os.path.join(folder2, 'mol.rtf')):
        prm1 = parmed.charmm.CharmmParameterSet(os.path.join(folder1, 'mol.rtf'), os.path.join(folder1, 'mol.prm'))
        prm2 = parmed.charmm.CharmmParameterSet(os.path.join(folder2, 'mol.rtf'), os.path.join(folder2, 'mol.prm'))
    else:
        raise RuntimeError('Could not find frcmod or prm/rtf combination in folders {} {}'.format(folder1, folder2))
    return mol1, prm1, prm2

def _parameterCompare(folder1, folder2, prm1, prm2, fields=('atom_types', 'bond_types', 'angle_types', 'improper_types', 'improper_periodic_types'), dihedrals=()):
    def myerror(msg):
        raise RuntimeError('Difference found in {} and {}. {}'.format(folder1, folder2, msg))

    def samekeys(d1, d2):
        for k1, k2 in zip(d1.keys(), d2.keys()):
            if k1 != k2:
                return False
        return True

    def comparevalues(val1, val2):
        if isinstance(val1, tuple) or isinstance(val1, list):
            same = True
            for v1, v2 in zip(val1, val2):
                same &= comparevalues(v1, v2)
            return same
        if isinstance(val1, dict):
            same = True
            if not samekeys(val1, val2):
                return False
            for v1, v2 in zip(val1.keys(), val2.keys()):
                same &= comparevalues(val1[v1], val2[v2])
            return same
        else:
            return val1 == val2

    def compareOrderedDict(name, od1, od2):
        if len(od1) != len(od2):
            myerror('Different number of {}'.format(name))
        for t1, t2 in zip(od1, od2):
            if t1 != t2:
                myerror('Different "{}" detected.'.format(name))
            for field in od1[t1].__dict__:
                same = comparevalues(od1[t1].__dict__[field], od2[t2].__dict__[field])
                if not same:
                    myerror('Different values for "{}" "{}" and field "{}"'.format(name, t1, field))

    if not samekeys(prm1.__dict__, prm2.__dict__):
        myerror('Different number of fields')

    for f in fields:
        compareOrderedDict(f, prm1.__dict__[f], prm2.__dict__[f])


class TestParameterize(unittest.TestCase):

    def setUp(self):
        if os.environ.get('TRAVIS_OS_NAME') == 'osx':
            self.skipTest('Mac does not work!')

        self.maxDiff = None
        self.dataDir = home(dataDir='test-param')
        self.testDir = os.environ.get('TESTDIR', tempname())

        print('\n') # Just for a better readability

    def _execute(self, refDir, resDir, cmd):
        if not os.path.exists(resDir):
            os.makedirs(resDir)

        molFile = os.path.join(refDir, 'input.mol2')
        if os.path.exists(molFile):
            shutil.copy(molFile, resDir)

        arguments = cmd.split()
        returncode = call(arguments, cwd=resDir)
        self.assertEqual(returncode, 0)

    def _testParametrizationEnergies(self, refDir, resDir, dihedrals=()):
        def _foldersToTest(refDir):
            folderstotest = []
            excluded = ('minimize', 'esp', 'dihedral')
            for root, dirs, _ in os.walk(refDir, followlinks=True):
                for d in dirs:
                    dname = os.path.relpath(os.path.join(root, d), start=refDir)
                    if dname in excluded:
                        continue
                    if os.path.exists(os.path.join(root, d, 'mol.frcmod')) or (
                        os.path.exists(os.path.join(root, d, 'mol.prm')) and os.path.exists(
                            os.path.join(root, d, 'mol.rtf'))):
                        folderstotest.append(dname)
            return folderstotest

        for f in _foldersToTest(refDir):
            folder1 = os.path.join(refDir, f)
            folder2 = os.path.join(resDir, f)
            mol, prm1, prm2 = _loadFiles(folder1, folder2)
            _parameterCompare(folder1, folder2, prm1, prm2, dihedrals=dihedrals)

    def _testFiles(self, refDir, resDir):
        filestotest = []
        excluded = ('minimize', 'esp', 'dihedral', '.coor', '.svg', '.frcmod', '.prm', '.rtf')
        for root, _, files in os.walk(refDir, followlinks=True):
            for file in files:
                flag = False
                relFile = os.path.relpath(os.path.join(root, file), start=refDir)
                for exc in excluded:
                    if relFile.startswith(exc) or relFile.endswith(exc):
                        flag = True
                if not flag:
                    filestotest.append(os.path.join(root, file))

        print('Compared files:')
        for file in filestotest:
            relFile = os.path.relpath(file, start=refDir)
            print('  %s' % relFile)

            refFile = os.path.join(refDir, relFile)
            resFile = os.path.join(resDir, relFile)

            with self.subTest(refFile=refFile):
                self.assertTrue(os.path.exists(resFile))

                with open(refFile) as ref, open(resFile) as res:
                    refLines, resLines = ref.readlines(), res.readlines()

                if file.endswith('energies.txt'):
                    refFields = [field for line in refLines for field in line.split()]
                    resFields = [field for line in resLines for field in line.split()]
                    for refField, resField in zip(refFields, resFields):
                        with self.subTest():
                            try:
                                refFloat = float(refField)
                                resFloat = float(resField)
                                self.assertAlmostEqual(refFloat, resFloat, places=4, msg=refFile)
                            except ValueError:
                                self.assertEqual(refField, resField, msg=refFile)
                else:
                    self.assertListEqual(refLines, resLines, msg=refFile)

        print('')

    def test_h2o2_list(self):
        refDir = os.path.join(self.dataDir, 'h2o2_list')
        resDir = os.path.join(self.testDir, 'h2o2_list')
        self._execute(refDir, resDir, 'parameterize input.mol2 -l')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_h2o2_gaff2(self):
        refDir = os.path.join(self.dataDir, 'h2o2_gaff2')
        resDir = os.path.join(self.testDir, 'h2o2_gaff2')
        self._execute(refDir, resDir, 'parameterize input.mol2 -f GAFF2 --no-min --no-esp --no-dihed')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_h2o2_outdir(self):
        refDir = os.path.join(self.dataDir, 'h2o2_outdir')
        resDir = os.path.join(self.testDir, 'h2o2_outdir')
        self._execute(refDir, resDir, 'parameterize input.mol2 -f GAFF2 --no-min --no-esp --no-dihed -o dir')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_h2o2_min(self):
        refDir = os.path.join(self.dataDir, 'h2o2_min')
        resDir = os.path.join(self.testDir, 'h2o2_min')
        self._execute(refDir, resDir, 'parameterize input.mol2 -f GAFF2 --no-esp --no-dihed')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_h2o2_min_restart(self):
        refDir = os.path.join(self.dataDir, 'h2o2_min_restart')
        resDir = os.path.join(self.testDir, 'h2o2_min_restart')
        shutil.copytree(os.path.join(refDir, 'minimize'), os.path.join(resDir, 'minimize'))
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-esp --no-dihed')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_h2o2_esp(self):
        refDir = os.path.join(self.dataDir, 'h2o2_esp')
        resDir = os.path.join(self.testDir, 'h2o2_esp')
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-dihed')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_h2o2_esp_restart(self):
        refDir = os.path.join(self.dataDir, 'h2o2_esp_restart')
        resDir = os.path.join(self.testDir, 'h2o2_esp_restart')
        shutil.copytree(os.path.join(refDir, 'esp'), os.path.join(resDir, 'esp'))
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-dihed')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(os.environ.get('HTMD_LONGTESTS') == 'yes', 'Too long')
    def test_h2o2_dihed_fix(self):
        refDir = os.path.join(self.dataDir, 'h2o2_dihed_fix')
        resDir = os.path.join(self.testDir, 'h2o2_dihed_fix')
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-esp --no-dihed-opt')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_h2o2_dihed_fix_restart(self):
        refDir = os.path.join(self.dataDir, 'h2o2_dihed_fix_restart')
        resDir = os.path.join(self.testDir, 'h2o2_dihed_fix_restart')
        shutil.copytree(os.path.join(refDir, 'dihedral-single-point'), os.path.join(resDir, 'dihedral-single-point'))
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-esp --no-dihed-opt')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(os.environ.get('HTMD_VERYLONGTESTS') == 'yes', 'Too long')
    def test_h2o2_dihed_opt(self):
        refDir = os.path.join(self.dataDir, 'h2o2_dihed_opt')
        resDir = os.path.join(self.testDir, 'h2o2_dihed_opt')
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-esp')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_h2o2_dihed_opt_restart(self):
        refDir = os.path.join(self.dataDir, 'h2o2_dihed_opt_restart')
        resDir = os.path.join(self.testDir, 'h2o2_dihed_opt_restart')
        shutil.copytree(os.path.join(refDir, 'dihedral-opt'), os.path.join(resDir, 'dihedral-opt'))
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-esp')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(sys.version_info.major == 3 and sys.version_info.minor > 5, 'Python 3.5 issue')
    def test_h2o2_full_fake(self):
        refDir = os.path.join(self.dataDir, 'h2o2_full_fake')
        resDir = os.path.join(self.testDir, 'h2o2_full_fake')
        self._execute(refDir, resDir, 'parameterize input.mol2 --fake-qm')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(sys.version_info.major == 3 and sys.version_info.minor > 5, 'Python 3.5 issue')
    def test_h2o2_full_fake_restart(self):
        refDir = os.path.join(self.dataDir, 'h2o2_full_fake_restart')
        resDir = os.path.join(self.testDir, 'h2o2_full_fake_restart')
        shutil.copytree(os.path.join(refDir, 'minimize'), os.path.join(resDir, 'minimize'))
        shutil.copytree(os.path.join(refDir, 'esp'), os.path.join(resDir, 'esp'))
        shutil.copytree(os.path.join(refDir, 'dihedral-opt'), os.path.join(resDir, 'dihedral-opt'))
        self._execute(refDir, resDir, 'parameterize input.mol2 --fake-qm')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(os.environ.get('HTMD_VERYLONGTESTS') == 'yes', 'Too long')
    def test_ethene_dihed_fix(self):
        refDir = os.path.join(self.dataDir, 'ethene_dihed_fix')
        resDir = os.path.join(self.testDir, 'ethene_dihed_fix')
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-esp --no-dihed-opt')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_ethene_dihed_fix_restart(self):
        refDir = os.path.join(self.dataDir, 'ethene_dihed_fix')
        resDir = os.path.join(self.testDir, 'ethene_dihed_fix_restart')
        shutil.copytree(os.path.join(refDir, 'dihedral-single-point'), os.path.join(resDir, 'dihedral-single-point'))
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-esp --no-dihed-opt')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(os.environ.get('HTMD_VERYLONGTESTS') == 'yes', 'Too long')
    def test_glycol_dihed_fix(self):
        refDir = os.path.join(self.dataDir, 'glycol_dihed_fix')
        resDir = os.path.join(self.testDir, 'glycol_dihed_fix')
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-esp --no-dihed-opt')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_glycol_dihed_fix_restart(self):
        refDir = os.path.join(self.dataDir, 'glycol_dihed_fix')
        resDir = os.path.join(self.testDir, 'glycol_dihed_fix_restart')
        shutil.copytree(os.path.join(refDir, 'dihedral-single-point'), os.path.join(resDir, 'dihedral-single-point'))
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-esp --no-dihed-opt')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_glycol_dihed_fix_restart_2(self):

        refDir = os.path.join(self.dataDir, 'glycol_dihed_fix')
        resDir = tempname()
        shutil.copytree(os.path.join(refDir, 'dihedral-single-point'), os.path.join(resDir, 'dihedral-single-point'))
        dihedrals = ['O1-C1-C2-O2', 'C1-C2-O2-H6']
        self._execute(refDir, resDir, 'parameterize input.mol2 -d {} --no-min --no-esp --no-dihed-opt'.format(' '.join(dihedrals)))
        self._testParametrizationEnergies(refDir, resDir, dihedrals=dihedrals)
        self._testFiles(refDir, resDir)

    def test_glycol_dihed_select_1_restart(self):
        refDir = os.path.join(self.dataDir, 'glycol_dihed_select_1_restart')
        resDir = os.path.join(self.testDir, 'glycol_dihed_select_1_restart')
        shutil.copytree(os.path.join(refDir, 'dihedral-single-point'), os.path.join(resDir, 'dihedral-single-point'))
        dihedrals = ['O1-C1-C2-O2',]
        self._execute(refDir, resDir, 'parameterize input.mol2 -d {} --no-min --no-esp --no-dihed-opt'.format(' '.join(dihedrals)))
        self._testParametrizationEnergies(refDir, resDir, dihedrals=dihedrals)
        self._testFiles(refDir, resDir)

    def test_glycol_dihed_select_2_restart(self):
        refDir = os.path.join(self.dataDir, 'glycol_dihed_select_2_restart')
        resDir = os.path.join(self.testDir, 'glycol_dihed_select_2_restart')
        shutil.copytree(os.path.join(refDir, 'dihedral-single-point'), os.path.join(resDir, 'dihedral-single-point'))
        dihedrals = ['C1-C2-O2-H6',]
        self._execute(refDir, resDir, 'parameterize input.mol2 -d {} --no-min --no-esp --no-dihed-opt'.format(' '.join(dihedrals)))
        self._testParametrizationEnergies(refDir, resDir, dihedrals=dihedrals)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(os.environ.get('HTMD_VERYLONGTESTS') == 'yes', 'Too long')
    def test_ethanolamine_dihed_fix(self):
        refDir = os.path.join(self.dataDir, 'ethanolamine_dihed_fix')
        resDir = os.path.join(self.testDir, 'ethanolamine_dihed_fix')
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-esp --no-dihed-opt')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(os.environ.get('HTMD_LONGTESTS') == 'yes', 'Too long')
    def test_ethanolamine_dihed_fix_restart(self):
        refDir = os.path.join(self.dataDir, 'ethanolamine_dihed_fix_restart')
        resDir = os.path.join(self.testDir, 'ethanolamine_dihed_fix_restart')
        shutil.copytree(os.path.join(refDir, 'dihedral-single-point'), os.path.join(resDir, 'dihedral-single-point'))
        self._execute(refDir, resDir, 'parameterize input.mol2 --no-min --no-esp --no-dihed-opt')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_benzamidine_gaff(self):
        refDir = os.path.join(self.dataDir, 'benzamidine_gaff')
        resDir = os.path.join(self.testDir, 'benzamidine_gaff')
        self._execute(refDir, resDir, 'parameterize input.mol2 -c 1 -ff GAFF --no-min --no-esp --no-dihed')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_benzamidine_gaff2(self):
        refDir = os.path.join(self.dataDir, 'benzamidine_gaff2')
        resDir = os.path.join(self.testDir, 'benzamidine_gaff2')
        self._execute(refDir, resDir, 'parameterize input.mol2 -c 1 -ff GAFF2 --no-min --no-esp --no-dihed')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_benzamidine_cgenff(self):
        refDir = os.path.join(self.dataDir, 'benzamidine_cgenff')
        resDir = os.path.join(self.testDir, 'benzamidine_cgenff')
        self._execute(refDir, resDir, 'parameterize input.mol2 -c 1 -ff CGENFF --no-min --no-esp --no-dihed')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    def test_benzamidine_rtf_prm(self):
        refDir = os.path.join(self.dataDir, 'benzamidine_rtf_prm')
        resDir = os.path.join(self.testDir, 'benzamidine_rtf_prm')
        os.makedirs(resDir)
        shutil.copy(os.path.join(refDir, 'input.rtf'), resDir)
        shutil.copy(os.path.join(refDir, 'input.prm'), resDir)
        self._execute(refDir, resDir, 'parameterize input.mol2 -c 1 -ff CGENFF --rtf-prm input.rtf input.prm --no-min --no-esp --no-dihed')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(os.environ.get('HTMD_VERYLONGTESTS') == 'yes', 'Too long')
    def test_benzamidine_full(self):
        assert 'HTMD_CONFIG' in os.environ, '"HTMD_CONFIG" environment variable has to be set'
        refDir = os.path.join(self.dataDir, 'benzamidine_full')
        resDir = os.path.join(self.testDir, 'benzamidine_full')
        self._execute(refDir, resDir, 'parameterize input.mol2 -c 1 -ff GAFF2 CGENFF --basis 6-31G* -q Slurm')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(os.environ.get('HTMD_LONGTESTS') == 'yes', 'Too long')
    @unittest.skipUnless(os.environ.get('HTMD_UNSTABLETESTS') == 'yes', 'Unstable')
    def test_benzamidine_full_restart(self):

        refDir = os.path.join(self.dataDir, 'benzamidine_full_restart')
        resDir = os.path.join(self.testDir, 'benzamidine_full_restart')
        shutil.copytree(os.path.join(refDir, 'minimize'), os.path.join(resDir, 'minimize'))
        shutil.copytree(os.path.join(refDir, 'esp'), os.path.join(resDir, 'esp'))
        shutil.copytree(os.path.join(refDir, 'dihedral-opt'), os.path.join(resDir, 'dihedral-opt'))
        self._execute(refDir, resDir, 'parameterize input.mol2 -c 1 -ff GAFF2 CGENFF --basis 6-31G*')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(os.environ.get('HTMD_UNSTABLETESTS') == 'yes', 'Unstable')
    def test_benzamidine_esp_freeze_restart(self):

        refDir = os.path.join(self.dataDir, 'benzamidine_esp_freeze_restart')
        resDir = os.path.join(self.testDir, 'benzamidine_esp_freeze_restart')
        shutil.copytree(os.path.join(refDir, 'minimize'), os.path.join(resDir, 'minimize'))
        shutil.copytree(os.path.join(refDir, 'esp'), os.path.join(resDir, 'esp'))
        self._execute(refDir, resDir, 'parameterize input.mol2 -c 1 -ff GAFF2 CGENFF --fix-charge N2 --basis 6-31G* --no-dihed')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)

    @unittest.skipUnless(os.environ.get('HTMD_UNSTABLETESTS') == 'yes', 'Unstable')
    def test_benzamidine_dihed_select_restart(self):

        refDir = os.path.join(self.dataDir, 'benzamidine_dihed_select_restart')
        resDir = os.path.join(self.testDir, 'benzamidine_dihed_select_restart')
        shutil.copytree(os.path.join(refDir, 'minimize'), os.path.join(resDir, 'minimize'))
        shutil.copytree(os.path.join(refDir, 'esp'), os.path.join(resDir, 'esp'))
        shutil.copytree(os.path.join(refDir, 'dihedral-opt'), os.path.join(resDir, 'dihedral-opt'))
        self._execute(refDir, resDir, 'parameterize input.mol2 -c 1 -ff GAFF2 CGENFF -d C2-C1-C7-N1 --basis 6-31G*')
        self._testParametrizationEnergies(refDir, resDir)
        self._testFiles(refDir, resDir)


if __name__ == '__main__':
    unittest.main(verbosity=2)

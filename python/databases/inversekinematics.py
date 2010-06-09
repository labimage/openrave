#!/usr/bin/env python
# Copyright (C) 2009-2010 Rosen Diankov (rosen.diankov@gmail.com)
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import with_statement # for python 2.5
__author__ = 'Rosen Diankov'
__copyright__ = 'Copyright (C) 2009-2010 Rosen Diankov (rosen.diankov@gmail.com)'
__license__ = 'Apache License, Version 2.0'

from openravepy import *
from openravepy.interfaces import BaseManipulation
from openravepy import ikfast
from numpy import *
import time,platform,shutil
import distutils
from distutils import ccompiler
from optparse import OptionParser

class InverseKinematicsModel(OpenRAVEModel):
    """Generates analytical inverse-kinematics solutions, compiles them into a shared object/DLL, and sets the robot's iksolver. Only generates the models for the robot's active manipulator. To generate IK models for each manipulator in the robot, mulitple InverseKinematicsModel classes have to be created."""
    def __init__(self,robot,iktype=None):
        OpenRAVEModel.__init__(self,robot=robot)
        self.iktype = iktype
        self.iksolver = None
        self.freeinc = None
    def clone(self,envother):
        clone = OpenRAVEModel.clone(self,envother)
        clone.setrobot(self.freeinc)
        return clone    
    def has(self):
        return self.iksolver is not None and self.manip.HasIKSolver()
    def load(self,*args,**kwargs):
        return self.setrobot(*args,**kwargs)
    def getversion(self):
        return 3
    def setrobot(self,freeinc=None):
        self.iksolver = None
        self.freeinc=freeinc
        if freeinc is not None:
            iksuffix = ' %f'%freeinc
        else:
            iksuffix = ''
#         if self.manip.HasIKSolver():
#             self.iksolver = self.env.CreateIkSolver(self.manip.GetIKSolverName()+iksuffix) if self.manip.HasIKSolver() else None
        if self.iksolver is None:
            with self.env:
                ikfastproblem = [p for p in self.env.GetLoadedProblems() if p.GetXMLId() == 'IKFast'][0]
                ikname = 'ikfast.%s.%s'%(self.robot.GetRobotStructureHash(),self.manip.GetName())
                iktype = ikfastproblem.SendCommand('AddIkLibrary %s %s'%(ikname,self.getfilename()))
                if iktype is None:
                    self.iksolver = self.env.CreateIkSolver(self.manip.GetIKSolverName()+iksuffix) if self.manip.HasIKSolver() else None
                else:
                    if int(self.iktype) != int(iktype):
                        raise ValueError('ik does not match types %s!=%s'%(self.iktype,iktype))
                    self.iksolver = self.env.CreateIkSolver(ikname+iksuffix)
        if self.iksolver is not None:
            self.manip.SetIKSolver(self.iksolver)
            if not self.manip.InitIKSolver():
                return False
        return self.has()
    
    def save(self):
        pass # already saved as a lib
    
    def getfilename(self):
        basename = 'ikfast' + str(self.getversion()) + '.' + self.manip.GetStructureHash() + '.' + str(self.iktype) + '.' + platform.machine()
        return ccompiler.new_compiler().shared_object_filename(basename=basename,output_dir=OpenRAVEModel.getfilename(self))
    def getsourcefilename(self):
        return os.path.join(OpenRAVEModel.getfilename(self),'ikfast' + str(self.getversion()) + '.' + self.manip.GetStructureHash() + '.' + str(self.iktype))
    def autogenerate(self,options=None):
        freejoints = None
        iktype = None
        usedummyjoints = None
        accuracy = None
        precision = None
        forceikbuild = False
        if options is not None:
            if options.rotation3donly:
                iktype = IkParameterization.Type.Rotation3D
            if options.direction3donly:
                iktype = IkParameterization.Type.Direction3D
            if options.translation3donly:
                iktype = IkParameterization.Type.Translation3D
            if options.ray4donly:
                iktype = IkParameterization.Type.Ray4D
            forceikbuild=options.force
            precision=options.precision
            accuracy=options.accuracy
            usedummyjoints=options.usedummyjoints
            if options.freejoints is not None:
                freejoints=options.freejoints
        if self.robot.GetKinematicsGeometryHash() == '0d258d45aacb7ea4f6f88c4602d4b077' or self.robot.GetKinematicsGeometryHash() == '2c7f45a52ae3cbd4c0663d8abbd5f020': # wam 7dof
            if freejoints is None:
                freejoints = ['Shoulder_Roll']
        elif self.robot.GetKinematicsGeometryHash() == '2950e0e6064bda0a68145750363b6f79': # wam 4dof
            if freejoints is None:
                freejoints = ['Shoulder_Roll']
            if iktype is None:
                iktype=IkParameterization.Type.Translation3D
        elif self.robot.GetRobotStructureHash() == '7d30ec51a4b393b08f7febca4b9abd34': # stage
            if iktype is None:
                iktype=IkParameterization.Type.Rotation3D
        elif self.robot.GetRobotStructureHash() == 'bec5e13f7bc7f7fcc3e07e8a82522bee': # pr2
            if iktype is None:
                if self.manip.GetName().find('camera') >= 0:
                    # cameras are attached, so use a ray parameterization
                    iktype=IkParameterization.Type.Ray4D
                else:
                    iktype=IkParameterization.Type.Transform6D
            if freejoints is None:
                # take the first joints
                jointinds=self.manip.GetArmJoints()[0:(len(self.manip.GetArmJoints())-6)]
                freejoints=[self.robot.GetJoints()[ind].GetName() for ind in jointinds]
        self.generate(iktype=iktype,freejoints=freejoints,usedummyjoints=usedummyjoints,accuracy=accuracy,precision=precision,forceikbuild=forceikbuild)
        self.save()

    def generate(self,iktype=None,freejoints=None,usedummyjoints=False,accuracy=None,precision=None,forceikbuild=False):
        if iktype is not None:
            self.iktype = iktype
        if self.iktype is None:
            self.iktype = iktype = IkParameterization.Type.Transform6D
        output_filename = self.getfilename()
        sourcefilename = self.getsourcefilename()
        if self.iktype == IkParameterization.Type.Rotation3D:
            solvefn=ikfast.IKFastSolver.solveFullIK_Rotation3D
        elif self.iktype == IkParameterization.Type.Direction3D:
            basedir=dot(self.manip.GetGraspTransform()[0:3,0:3],self.manip.GetDirection())
            def solveFullIK_Direction3D(*args,**kwargs):
                kwargs['basedir'] = basedir
                return ikfast.IKFastSolver.solveFullIK_Direction3D(*args,**kwargs)
            solvefn=solveFullIK_Direction3D
        elif self.iktype == IkParameterization.Type.Ray4D:
            basedir=dot(self.manip.GetGraspTransform()[0:3,0:3],self.manip.GetDirection())
            basepos=self.manip.GetGraspTransform()[0:3,3]
            def solveFullIK_Ray4D(*args,**kwargs):
                kwargs['basedir'] = basedir
                kwargs['basepos'] = basepos
                return ikfast.IKFastSolver.solveFullIK_Ray4D(*args,**kwargs)
            solvefn=solveFullIK_Ray4D
        elif self.iktype == IkParameterization.Type.Translation3D:
            solvefn=ikfast.IKFastSolver.solveFullIK_Translation3D
        elif self.iktype == IkParameterization.Type.Transform6D:
            solvefn=ikfast.IKFastSolver.solveFullIK_6D
        else:
            raise ValueError('bad type')
        solvejoints = list(self.manip.GetArmJoints())
        freejointinds = []
        if freejoints is not None:
            for jointname in freejoints:
                if type(jointname) == int:
                    freejointinds.append(jointname)
                    solvejoints.remove(jointname)
                else:
                    # find the correct joint index
                    freejointinds.append([joint.GetJointIndex() for joint in self.robot.GetJoints() if joint.GetName()==jointname][0])
                    solvejoints.remove(freejointinds[-1])
        print 'Generating inverse kinematics for manip',self.manip.GetName(),':',self.iktype,solvejoints,'(this might take ~10 min)'
        if self.iktype == IkParameterization.Type.Rotation3D:
            self.dofexpected = 3
        elif self.iktype == IkParameterization.Type.Direction3D:
            self.dofexpected = 2
        elif self.iktype == IkParameterization.Type.Translation3D:
            self.dofexpected = 3
        elif self.iktype == IkParameterization.Type.Transform6D:
            self.dofexpected = 6
        elif self.iktype == IkParameterization.Type.Ray4D:
            self.dofexpected = 4
        else:
            raise ValueError('bad type')

        if len(solvejoints) > self.dofexpected:
            for i in range(len(solvejoints) - self.dofexpected):
                if self.dofexpected == 6:
                    freejointinds.append(solvejoints.pop(2))
                else:
                    freejointinds.append(solvejoints.pop(0))
        
        if not len(solvejoints) == self.dofexpected:
            raise ValueError('Need %d solve joints, got: %d'%(self.dofexpected, len(solvejoints)))
        
        sourcefilename += '_' + '_'.join(str(ind) for ind in solvejoints)
        if len(freejointinds)>0:
            sourcefilename += '_f'+'_'.join(str(ind) for ind in freejointinds)
        sourcefilename += '.cpp'
        if forceikbuild or not os.path.isfile(sourcefilename):
            print 'generating inverse kinematics file %s'%sourcefilename
            mkdir_recursive(OpenRAVEModel.getfilename(self))
            solver = ikfast.IKFastSolver(kinbody=self.robot,accuracy=accuracy,precision=precision)
            code = solver.generateIkSolver(self.manip.GetBase().GetIndex(),self.manip.GetEndEffector().GetIndex(),solvejoints=solvejoints,freeparams=freejointinds,usedummyjoints=usedummyjoints,solvefn=solvefn)
            if len(code) == 0:
                raise ValueError('failed to generate ik solver for robot %s:%s'%(self.robot.GetName(),self.manip.GetName()))
            open(sourcefilename,'w').write(code)
        
        # compile the code and create the shared object
        compiler,compile_flags = self.getcompiler()
        try:
           output_dir = os.path.relpath('/',os.getcwd())
        except AttributeError: # python 2.5 does not have os.path.relpath
           output_dir = self.myrelpath('/',os.getcwd())

        platformsourcefilename = os.path.splitext(output_filename)[0]+'.cpp' # needed in order to prevent interference with machines with different architectures 
        shutil.copyfile(sourcefilename, platformsourcefilename)
        try:
            objectfiles = compiler.compile(sources=[platformsourcefilename],macros=[('IKFAST_CLIBRARY',1)],extra_postargs=compile_flags,output_dir=output_dir)
            compiler.link_shared_object(objectfiles,output_filename=output_filename)
            if not self.load():
                return ValueError('failed to generate ik solver')
        finally:
            # cleanup intermediate files
            os.remove(platformsourcefilename)
            for objectfile in objectfiles:
                os.remove(objectfile)

    def testik(self,numiktests):
        with self.robot:
            # set base to identity to avoid complications when reporting errors
            self.robot.SetTransform(dot(linalg.inv(self.manip.GetBase().GetTransform()),self.robot.GetTransform()))
            lower,upper = [v[self.manip.GetArmJoints()] for v in self.robot.GetJointLimits()]
            if self.iktype == IkParameterization.Type.Direction3D:
                success = 0.0
                for i in range(numiktests):
                    while True:
                        self.robot.SetJointValues(random.rand()*(upper-lower)+lower,self.manip.GetArmJoints()) # set random values
                        if not self.robot.CheckSelfCollision():
                            break
                    orgvalues = self.robot.GetJointValues()[self.manip.GetArmJoints()]
                    targetdir = dot(self.manip.GetEndEffectorTransform()[0:3,0:3],self.manip.GetDirection())
                    self.robot.SetJointValues(random.rand()*(upper-lower)+lower,self.manip.GetArmJoints()) # set random values
                    sol = self.manip.FindIKSolution(IkParameterization(targetdir,self.iktype),False)
                    if sol is not None:
                        self.robot.SetJointValues(sol,self.manip.GetArmJoints())
                        realdir = dot(self.manip.GetEndEffectorTransform()[0:3,0:3],self.manip.GetDirection())
                        if sum((targetdir-realdir)**2) < 1e-7:
                            success += 1
                        else:
                            print 'wrong solution to: ',targetpos, 'returned is: ',realpos
                    else:
                        print 'failed to find: ',targetpos,'solution is: ',orgvalues
                return success/numiktests
            elif self.iktype == IkParameterization.Type.Translation3D:
                success = 0.0
                for i in range(numiktests):
                    while True:
                        self.robot.SetJointValues(random.rand()*(upper-lower)+lower,self.manip.GetArmJoints()) # set random values
                        if not self.robot.CheckSelfCollision():
                            break
                    orgvalues = self.robot.GetJointValues()[self.manip.GetArmJoints()]
                    targetpos = self.manip.GetEndEffectorTransform()[0:3,3]
                    #self.robot.SetJointValues(random.rand()*(upper-lower)+lower,self.manip.GetArmJoints()) # set random values
                    sol = self.manip.FindIKSolution(IkParameterization(targetpos,self.iktype),False)
                    if sol is not None:
                        self.robot.SetJointValues(sol,self.manip.GetArmJoints())
                        realpos = self.manip.GetEndEffectorTransform()[0:3,3]
                        if sum((targetpos-realpos)**2) < 1e-7:
                            success += 1
                        else:
                            print 'wrong solution to: ',targetpos, 'returned is: ',realpos
                    else:
                        print 'failed to find: ',targetpos,'solution is: ',orgvalues
                return success/numiktests
            elif self.iktype == IkParameterization.Type.Rotation3D:
                success = 0.0
                for i in range(numiktests):
                    while True:
                        self.robot.SetJointValues(random.rand()*(upper-lower)+lower,self.manip.GetArmJoints()) # set random values
                        if not self.robot.CheckSelfCollision():
                            break
                    orgvalues = self.robot.GetJointValues()[self.manip.GetArmJoints()]
                    targetquat = quatFromRotationMatrix(self.manip.GetEndEffectorTransform()[0:3,0:3])
                    self.robot.SetJointValues(random.rand()*(upper-lower)+lower,self.manip.GetArmJoints()) # set random values
                    sol = self.manip.FindIKSolution(IkParameterization(targetquat,self.iktype),False)
                    if sol is not None:
                        self.robot.SetJointValues(sol,self.manip.GetArmJoints())
                        realquat = quatFromRotationMatrix(self.manip.GetEndEffectorTransform()[0:3,0:3])
                        if quatArrayTDist(targetquat,realquat) < 1e-3:
                            success += 1
                        else:
                            print 'wrong solution to: ',targetquat, 'returned is: ',realquat
                    else:
                        print 'failed to find: ',targetquat,'solution is: ',orgvalues
                return success/numiktests
            elif self.iktype == IkParameterization.Type.Ray4D:
                success = 0.0
                self.robot.Enable(False)
                for i in range(numiktests):
                    while True:
                        self.robot.SetJointValues(random.rand()*(upper-lower)+lower,self.manip.GetArmJoints()) # set random values
                        if not self.robot.CheckSelfCollision():
                            break
                    orgvalues = self.robot.GetJointValues()[self.manip.GetArmJoints()]
                    targetdir = dot(self.manip.GetEndEffectorTransform()[0:3,0:3],self.manip.GetDirection())
                    targetpos = self.manip.GetEndEffectorTransform()[0:3,3]
                    targetpos += (random.rand()-0.5)*sqrt(sum(targetpos**2))*targetdir
                    #print targetdir[0],targetdir[1],targetdir[2],targetpos[0],0,0,0,targetpos[1],0,0,0,targetpos[2]
                    targetprojpos = targetpos - targetdir*dot(targetdir,targetpos)
                    self.robot.SetJointValues(random.rand()*(upper-lower)+lower,self.manip.GetArmJoints()) # set random values
                    sol = self.manip.FindIKSolution(IkParameterization(Ray(targetpos,targetdir),self.iktype),False)
                    if sol is not None:
                        self.robot.SetJointValues(sol,self.manip.GetArmJoints())
                        realdir = dot(self.manip.GetEndEffectorTransform()[0:3,0:3],self.manip.GetDirection())
                        realpos = self.manip.GetEndEffectorTransform()[0:3,3]
                        realprojpos = realpos - realdir*dot(realdir,realpos)
                        if sum((targetdir-realdir)**2) < 2e-5 and sum((targetprojpos-realprojpos)**2) < 1e-6:
                            success += 1
                        else:
                            print 'wrong solution to: ',targetpos,targetdir, 'returned is: ',realpos,realdir,'wrong sol is:',sol,', org values are:',orgvalues
                            print sum((targetdir-realdir)**2), sum((targetprojpos-realprojpos)**2)
                    else:
                        print 'failed to find: ',targetpos,targetdir,'solution is: ',orgvalues
                return success/numiktests
            else:
                basemanip = BaseManipulation(self.robot)
                successrate = basemanip.DebugIK(numiters=numiktests)
        return successrate

    @staticmethod
    def getcompiler():
        compiler = ccompiler.new_compiler()
        compile_flags = []
        if compiler.compiler_type == 'msvc':
            compile_flags.append('/Ox')
            try:
                # make sure it is correct version!
                cname,cver = openravepyCompilerVersion().split()
                if cname == 'msvc':
                    majorVersion = int(cver)/100-6
                    minorVersion = mod(int(cver),100)/10.0
                    if abs(compiler._MSVCCompiler__version - majorVersion+minorVersion) > 0.001:
                        # not the same version, look for a different compiler
                        distutils.msvc9compiler.VERSION = majorVersion + minorVersion
                        newcompiler = ccompiler.new_compiler()
                        if newcompiler is not None:
                            compiler = newcompiler
            except:
                pass
        else:
            compiler.add_library('stdc++')
            if compiler.compiler_type == 'unix':
                compile_flags.append('-O3')
                compile_flags.append('-fPIC')
        return compiler,compile_flags

    @staticmethod
    def myrelpath(path, start=os.path.curdir):
        """Return a relative version of a path"""
        if not path:
            raise ValueError("no path specified")

        start_list = os.path.abspath(start).split(os.path.sep)
        path_list = os.path.abspath(path).split(os.path.sep)

        # Work out how much of the filepath is shared by start and path.
        i = len(os.path.commonprefix([start_list, path_list]))

        rel_list = [os.path.pardir] * (len(start_list)-i) + path_list[i:]
        if not rel_list:
            return os.path.curdir
        return os.path.join(*rel_list)

    @staticmethod
    def CreateOptionParser():
        parser = OpenRAVEModel.CreateOptionParser()
        parser.description='Computes the closed-form inverse kinematics equations of a robot manipulator, generates a C++ file, and compiles this file into a shared object which can then be loaded by OpenRAVE'
        parser.add_option('--freejoint', action='append', type='string', dest='freejoints',default=None,
                          help='Optional joint name specifying a free parameter of the manipulator. If nothing specified, assumes all joints not solving for are free parameters. Can be specified multiple times for multiple free parameters.')
        parser.add_option('--precision', action='store', type='int', dest='precision',default=10,
                          help='The precision to compute the inverse kinematics in, (default=%default).')
        parser.add_option('--accuracy', action='store', type='float', dest='accuracy',default=1e-7,
                          help='The small number that will be recognized as a zero used to eliminate floating point errors (default=%default).')
        parser.add_option('--force', action='store_true', dest='force',default=False,
                          help='If set, will always rebuild the ikfast c++ file, regardless of its existence (default=%default).')
        parser.add_option('--rotation3donly', action='store_true', dest='rotation3donly',default=False,
                          help='If true, need to specify only 3 solve joints and will solve for a target rotation')
        parser.add_option('--direction3donly', action='store_true', dest='direction3donly',default=False,
                          help='If true, need to specify only 2 solve joints and will solve for a target direction')
        parser.add_option('--translation3donly', action='store_true', dest='translation3donly',default=False,
                          help='If true, need to specify only 3 solve joints and will solve for a target translation')
        parser.add_option('--ray4donly', action='store_true', dest='ray4donly',default=False,
                          help='If true, need to specify only 4 solve joints and will solve for a target ray')
        parser.add_option('--usedummyjoints', action='store_true',dest='usedummyjoints',default=False,
                          help='Treat the unspecified joints in the kinematic chain as dummy and set them to 0. If not specified, treats all unspecified joints as free parameters.')
        parser.add_option('--freeinc', action='store', type='float', dest='freeinc',default=None,
                          help='The discretization value of freejoints.')
        parser.add_option('--numiktests', action='store',type='int',dest='numiktests',default=None,
                          help='Will test the ik solver against NUMIKTESTS random robot configurations and program will exit with 0 if success rate exceeds the test success rate, otherwise 1.')
        return parser
    @staticmethod
    def RunFromParser(Model=None,parser=None):
        if parser is None:
            parser = InverseKinematicsModel.CreateOptionParser()
        (options, args) = parser.parse_args()
        Model = lambda robot: InverseKinematicsModel(robot=robot)
        OpenRAVEModel.RunFromParser(Model=Model,parser=parser)

        if options.numiktests is not None:
            print 'testing the success rate of robot ',options.robot
            env = Environment()
            try:
                robot = env.ReadRobotXMLFile(options.robot)
                env.AddRobot(robot)
                iktype = IkParameterization.Type.Transform6D
                if options.rotation3donly:
                    iktype = IkParameterization.Type.Rotation3D
                if options.direction3donly:
                    iktype = IkParameterization.Type.Direction3D
                if options.translation3donly:
                    iktype = IkParameterization.Type.Translation3D
                if options.ray4donly:
                    iktype = IkParameterization.Type.Ray4D
                if options.manipname is not None:
                    robot.SetActiveManipulator(options.manipname)
                ikmodel = InverseKinematicsModel(robot,iktype=iktype)
                if not ikmodel.setrobot(freeinc=options.freeinc):
                    raise ValueError('failed to load ik')
                successrate = ikmodel.testik(numiktests=options.numiktests)
                print 'success rate is: ',successrate
            finally:
                env.Destroy()

if __name__ == "__main__":
     InverseKinematicsModel.RunFromParser()
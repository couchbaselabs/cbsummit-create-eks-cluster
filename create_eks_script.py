import subprocess
import parameters
import sys
import time
import os
from tempfile import mkstemp
from shutil import move

#=======================================
#	Constants
#=======================================
ns=""
divider="--------------------------------------"
version="1.0.1"

#=======================================
#	Variables
#=======================================
step=0
vpc_output=False
node_output=False
aws_values={}

#=======================================
#	Functions
#=======================================
def setAwsProfile(profile):
	os.environ['AWS_DEFAULT_PROFILE']=profile
	print("AWS_DEFAULT_PROFILE set to : {}".format(os.environ['AWS_DEFAULT_PROFILE']))

def onError(command, retval):
	print("Error detected:: ")
	print("command: {}".format(command))
	print("retval: {}".format(retval))
	sys.exit(retval)

def execute_command(command,ignore_error):
	print(divider)
	print("Executing command : {}".format(command))
	p=subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	for line in p.stdout.readlines():
		print(line)
	retval = p.wait()

	if retval != 0 and ignore_error == False:
		onError(command,retval)

def execute_command_with_status(command,ignore_error,status_command,status):
	print(divider)
	print("Running {}".format(command))

	execute_command(command,ignore_error)

	print("Checking completion status...")
	for x in range(parameters.ATTEMPTS):
		print("Checking attempt #{}".format(x))
		p=subprocess.Popen(status_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		for line in p.stdout.readlines():
			spaces=line.split()
			print("Status :: {}".format(spaces[0].decode('ascii')))
			if spaces[0].decode('ascii') == status:
				return 0
		retval = p.wait()
		time.sleep(parameters.WAIT_SEC)

	onError(command,retval)

def get_outputs(command,delimiter):
	global aws_values
	p=subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	for line in p.stdout.readlines():
		line=line.decode('ascii').rstrip()
		tokens=line.split(delimiter)
		print("Adding key {0} with value {1}".format(tokens[0],tokens[1]))
		aws_values[tokens[0]]=tokens[1]
	

def replace(file_path, pattern, subst):
	fh, abs_path = mkstemp()
	with os.fdopen(fh,'w') as new_file:
		with open(file_path) as old_file:
			for line in old_file:
				new_file.write(line.replace(pattern, subst))
	os.remove(file_path)
	move(abs_path, file_path)	

def insert_lines(file_path, pattern, subst):
	fh, abs_path = mkstemp()
	with os.fdopen(fh,'w') as new_file:
		with open(file_path) as old_file:
			for line in old_file:
				if line.rstrip() == pattern:
					for str in subst:
						new_file.write(str+"\n")
				new_file.write(line)
	os.remove(file_path)
	move(abs_path, file_path)

def usage():
	global version
	print("")
	print("python create_eks_script.py steps|delete|install [start step] [--profile aws_profile_name]")
	print("version: {}".format(version))
	print("")
	print("  --profile = Specify the aws profile to use for deployment")
	print("")
	print("  Install Steps:")
	print("   0. Create VPC")
	print("   1. Create EKS Cluster")
	print("   2. Configure kubectl")
	print("   3. Create worker nodes")
	print("   4. Pull aws-auth ConfigMap")
	print("   5. Update aws-auth and add nodes to cluster")
	print("   6. Patch aws-auth to grant secondary user access to EKS cluster")
	print("")
	print("  Delete Steps:")
	print("   0. Delete Worker Node Stack")
	print("   1. Delete EKS Cluster")
	print("   2. Delete VPC Stack")
	print("")
	sys.exit(0)

def install_eks():
	global step,vpc_output,node_output

	print(divider)
	print("Starting installation of EKS from step {}".format(step))	
	print(divider)

	if step == 0:
		rc = execute_command_with_status("aws cloudformation create-stack --stack-name {0} --template-url {1}".format(parameters.VPC_STACK_NAME,parameters.VPC_TEMPLATE), False,
			"aws cloudformation describe-stacks --stack-name {0} --query Stacks[0].StackStatus".format(parameters.VPC_STACK_NAME),"\"CREATE_COMPLETE\"")

		step=step+1

	if vpc_output == False and step >= 1:
		get_outputs("aws cloudformation describe-stacks --stack-name {0} --query Stacks[].Outputs[].[OutputKey,OutputValue] --output text".format(parameters.VPC_STACK_NAME),"\t")
		vpc_output=True

	if step == 1:
		rc = execute_command_with_status("aws eks create-cluster --name {0} --role-arn {1} --resources-vpc-config {2}".format(parameters.EKS_CLUSTER_NAME, parameters.EKS_ROLE_ARN, 
			"subnetIds={0},securityGroupIds={1}".format(aws_values["SubnetIds"],aws_values["SecurityGroups"])), False,
			"aws eks describe-cluster --name {0} --query cluster.status".format(parameters.EKS_CLUSTER_NAME),
			"\"ACTIVE\"")
		step=step+1

	if step == 2:
		rc = execute_command("aws eks update-kubeconfig --name {}".format(parameters.EKS_CLUSTER_NAME),False)
		step=step+1

	if step == 3:

		#Check Desired vs Min and Max
		if int(parameters.EKS_NODE_AS_GROUP_DESIRED) < int(parameters.EKS_NODE_AS_GROUP_MIN) or \
			int(parameters.EKS_NODE_AS_GROUP_DESIRED) > int(parameters.EKS_NODE_AS_GROUP_MAX):
			onError("Autoscaling Group Desired size outside Min/Max",1)

		#Build Worker Node Command
		command="aws cloudformation create-stack --stack-name {0} --template-url {1} --parameters \
ParameterKey=ClusterName,ParameterValue={2} ParameterKey=ClusterControlPlaneSecurityGroup,ParameterValue={3} \
ParameterKey=NodeGroupName,ParameterValue={4} ParameterKey=NodeAutoScalingGroupMinSize,ParameterValue={5} \
ParameterKey=NodeAutoScalingGroupMaxSize,ParameterValue={6} ParameterKey=NodeInstanceType,ParameterValue={7} \
ParameterKey=NodeImageId,ParameterValue={8} ParameterKey=KeyName,ParameterValue={9} \
ParameterKey=VpcId,ParameterValue={10} ParameterKey=Subnets,ParameterValue=\'{11}\' \
ParameterKey=NodeVolumeSize,ParameterValue={12} ParameterKey=NodeAutoScalingGroupDesiredCapacity,ParameterValue={13} \
 --capabilities CAPABILITY_IAM".format(parameters.EKS_NODES_STACK_NAME, parameters.EKS_NODES_TEMPLATE, 
parameters.EKS_CLUSTER_NAME, aws_values["SecurityGroups"],
parameters.EKS_NODE_GROUP_NAME, parameters.EKS_NODE_AS_GROUP_MIN,
parameters.EKS_NODE_AS_GROUP_MAX, parameters.EKS_NODE_INSTANCE_TYPE,
parameters.EKS_IMAGE_ID, parameters.EKS_KEY_NAME,
aws_values["VpcId"], aws_values["SubnetIds"].replace(",","\,"),
parameters.EKS_NODE_VOLUME_SIZE, parameters.EKS_NODE_AS_GROUP_DESIRED
)

		#execute command
		rc = execute_command_with_status(command,False,
			"aws cloudformation describe-stacks --stack-name {0} --query Stacks[0].StackStatus".format(parameters.EKS_NODES_STACK_NAME),"\"CREATE_COMPLETE\"")

		step=step+1

	if step == 4:
		execute_command("curl -O https://amazon-eks.s3-us-west-2.amazonaws.com/cloudformation/2018-12-10/aws-auth-cm.yaml", False)
		step=step+1


	if node_output == False and step >= 4:	
		get_outputs("aws cloudformation describe-stacks --stack-name {0} --query Stacks[].Outputs[].[OutputKey,OutputValue] --output text".format(parameters.EKS_NODES_STACK_NAME),"\t")

	if step == 5:
		replace("./aws-auth-cm.yaml","    - rolearn: <ARN of instance role (not instance profile)>","    - rolearn: {0}".format(aws_values["NodeInstanceRole"]))
		execute_command("kubectl apply -f aws-auth-cm.yaml", False)
		step=step+1

	try:
		AWS_SEC_ARN=parameters.AWS_SECOND_USER_ARN
		AWS_SEC_NAME=parameters.AWS_SECOND_USER_NAME
	except AttributeError:
		AWS_SEC_ARN=""
		AWS_SEC_NAME=""

	if step == 6 and len(AWS_SEC_ARN) > 3 and len(AWS_SEC_NAME) >= 1:
		execute_command("kubectl get -n kube-system configmap/aws-auth -o yaml > aws-auth-patch.yaml", False)
		insert_lines("./aws-auth-patch.yaml", "kind: ConfigMap",["  mapUsers: |","    - userarn: {}".format(parameters.AWS_SECOND_USER_ARN), \
				"      username: {}".format(parameters.AWS_SECOND_USER_NAME), \
				"      groups:", \
				"        - system:masters"])
		execute_command("kubectl apply -n kube-system -f aws-auth-patch.yaml",False)
	else:
		print("Skipping step 6 as incomplete secondary user credentials supplied in parameters file")


def delete_eks():
	global step
	print("Deleting from step {}".format(step))

	if step == 0:
		execute_command_with_status("aws cloudformation delete-stack --stack-name {} ".format(parameters.EKS_NODES_STACK_NAME), False, \
		"aws cloudformation describe-stacks --stack-name {} --query Stacks[0].StackStatus 2>&1 | grep -c \"does not exist\"".format(parameters.EKS_NODES_STACK_NAME), \
		"1")

		step=step+1

	if step == 1:
		execute_command_with_status("aws eks delete-cluster --name {} ".format(parameters.EKS_CLUSTER_NAME), True, \
		"aws eks describe-cluster --name {0} --query cluster.status 2>&1 | grep -c \"No cluster found\"".format(parameters.EKS_CLUSTER_NAME), \
		"1")

		step=step+1

	if step == 2:
		execute_command_with_status("aws cloudformation delete-stack --stack-name {} ".format(parameters.VPC_STACK_NAME), False, \
		"aws cloudformation describe-stacks --stack-name {} --query Stacks[0].StackStatus 2>&1 | grep -c \"does not exist\"".format(parameters.VPC_STACK_NAME), \
		"1")

		step=step+1

#=======================================
#	Main Program
#=======================================
if __name__ == "__main__":

	#=====================
	#Parse arguments
	#=====================
	if len(sys.argv) < 2:
		usage()

	mode="Unknown"
	x = 1
	while x < len(sys.argv):
		if sys.argv[x] == "steps":
			usage()
		elif sys.argv[x] == "install": 
			if mode == "Unknown":
				mode="install"
				x=x+1
				if x < len(sys.argv) and sys.argv[x].isdigit():
					step=int(sys.argv[x])
				else:
					x=x-1
		elif sys.argv[x] == "delete": 
			if mode == "Unknown":
				mode="delete"
				x=x+1
				if x < len(sys.argv) and sys.argv[x].isdigit():
					step=int(sys.argv[x])
				else:
					x=x-1
		elif sys.argv[x] == "--profile": 
			x=x+1
			if x < len(sys.argv):
				setAwsProfile(sys.argv[x])
		else:
			print("Unknown argument: {}".format(sys.argv[x]))
			usage()
		x=x+1	

	#==============================================================
	#Execute the script based on mode determined through arguments
	#==============================================================
	if mode == "Unknown":
		print("No execution mode specified.  Please specify install or delete")
		usage()
	elif mode == "install":
		install_eks()
	elif mode == "delete":
		delete_eks()

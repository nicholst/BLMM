import time
import os
import numpy as np
import scipy
from lib.tools3d import *
from lib.tools2d import *

def cSFS2D(XtX, XtY, ZtX, ZtY, ZtZ, XtZ, YtZ, YtY, YtX, nlevels, nparams, tol, n, init_paramVector):
  
  # Useful scalars
  # ------------------------------------------------------------------------------

  # Number of factors, r
  r = len(nlevels)

  # Number of random effects, q
  q = np.sum(np.dot(nparams,nlevels))

  # Number of fixed effects, p
  p = XtX.shape[0]


  # Index variables
  # ------------------------------------------------------------------------------
  # Work out the total number of paramateres
  tnp = np.int32(p + 1 + np.sum(nparams*(nparams+1)/2))

  # Indices for submatrics corresponding to Dks
  FishIndsDk = np.int32(np.cumsum(nparams*(nparams+1)/2) + p + 1)
  FishIndsDk = np.insert(FishIndsDk,0,p+1)
  #print('inds',FishIndsDk)

  # Work out D indices (there is one block of D per level)
  Dinds = np.zeros(np.sum(nlevels)+1)
  counter = 0
  for k in np.arange(len(nparams)):
    for j in np.arange(nlevels[k]):
      Dinds[counter] = np.concatenate((np.array([0]), np.cumsum(nlevels*nparams)))[k] + nparams[k]*j
      counter = counter + 1
      
  # Last index will be missing so add it
  Dinds[len(Dinds)-1]=Dinds[len(Dinds)-2]+nparams[-1]
  
  # Make sure indices are ints
  Dinds = np.int64(Dinds)

  # Duplication matrices
  # ------------------------------------------------------------------------------
  invDupMatdict = dict()
  invElimMatdict = dict()
  elimMatdict = dict()
  comMatdict = dict()
  for i in np.arange(len(nparams)):

    invDupMatdict[i] = invDupMat2D(nparams[i])
    invElimMatdict[i] = scipy.sparse.lil_matrix(np.linalg.pinv(elimMat2D(nparams[i]).toarray()))
    comMatdict[i] = comMat2D(nparams[i],nparams[i])
    elimMatdict[i] = elimMat2D(nparams[i])
    
  # Initial estimates
  # ------------------------------------------------------------------------------

  if init_paramVector is not None:

    #print(init_paramVector.shape)
    beta = init_paramVector[0:p]
    sigma2 = init_paramVector[p:(p+1)][0,0]

    Ddict = dict()
    cholDict = dict()
    for k in np.arange(len(nparams)):

      cholDict[k] = vechTri2mat2D(init_paramVector[FishIndsDk[k]:FishIndsDk[k+1]])
      Ddict[k] = cholDict[k] @ cholDict[k].transpose()
    
    # Matrix version
    D = scipy.sparse.lil_matrix((q,q))
    counter = 0
    for k in np.arange(len(nparams)):
      for j in np.arange(nlevels[i]):

        D[Dinds[counter]:Dinds[counter+1], Dinds[counter]:Dinds[counter+1]] = Ddict[k]
        counter = counter + 1

  else:

    # Inital beta
    beta = initBeta2D(XtX, XtY)

    # Work out e'e
    ete = ssr2D(YtX, YtY, XtX, beta)

    # Initial sigma2
    sigma2 = initSigma22D(ete, n)

    Zte = ZtY - (ZtX @ beta)
      
    # Inital D
    # Dictionary version
    Ddict = dict()
    cholDict = dict()

    for k in np.arange(len(nparams)):

      cholDict[k] = np.eye(nparams[k])
      Ddict[k] = np.eye(nparams[k])

    # Matrix version
    D = scipy.sparse.lil_matrix((q,q))
    t1 = time.time()
    counter = 0
    for k in np.arange(len(nparams)):
      for j in np.arange(nlevels[k]):

        D[Dinds[counter]:Dinds[counter+1], Dinds[counter]:Dinds[counter+1]] = Ddict[k]
        counter = counter + 1

    t2 = time.time()
    print('toDict time: ', t2-t1)

  Zte = ZtY - (ZtX @ beta)

  # Inverse of (I+Z'ZD) multiplied by DIplusDZtZ 
  IplusZtZD = np.eye(q) + ZtZ @ D
  t1 = time.time()
  DinvIplusZtZD = forceSym2D(D @ scipy.sparse.linalg.inv(scipy.sparse.csc_matrix(IplusZtZD)))
  t2 = time.time()
  print('inv time: ', t2-t1)

  # Step size lambda
  lam = 1
  
  # Initial log likelihoods
  llhprev = np.inf
  llhcurr = -np.inf
  
  # This will hold the matrices: Sum_j^{l_k} Z_{i,j}'Z_{i,j}
  ZtZmatdict = dict()
  for k in np.arange(len(nparams)):
    ZtZmatdict[k] = None

  # This will hold the permutations needed for the covariance between the
  # derivatives with respect to k
  permdict = dict()
  for k in np.arange(len(nparams)):
    permdict[str(k)] = None

  nit = 0
  while np.abs(llhprev-llhcurr)>tol:
    
    # Change current likelihood to previous
    llhprev = llhcurr

    #print(nit)
    nit = nit+1

    #---------------------------------------------------------------------------
    # Update beta
    beta = np.linalg.solve(XtX - XtZ @ DinvIplusZtZD @ ZtX, XtY - XtZ @ DinvIplusZtZD @ ZtY)
    
    # Update sigma^2
    ete = ssr2D(YtX, YtY, XtX, beta)
    Zte = ZtY - (ZtX @ beta)
    sigma2 = 1/n*(ete - Zte.transpose() @ DinvIplusZtZD @ Zte)
    
    # Update D_k
    counter = 0
    for k in np.arange(len(nparams)):

      # Work out derivative
      if ZtZmatdict[k] is None:
        dldD,ZtZmatdict[k] = get_dldDk2D(k, nlevels, nparams, ZtZ, Zte, sigma2, DinvIplusZtZD,ZtZmat=None)
      else:
        dldD,_ = get_dldDk2D(k, nlevels, nparams, ZtZ, Zte, sigma2, DinvIplusZtZD,ZtZmat=ZtZmatdict[k])

      # Work out update amount
      if permdict[str(k)] is None:
        covdldDk,permdict[str(k)] = get_covdldDk1Dk22D(k, k, nlevels, nparams, ZtZ, DinvIplusZtZD, invDupMatdict, perm=None)
      else:
        covdldDk,_ = get_covdldDk1Dk22D(k, k, nlevels, nparams, ZtZ, DinvIplusZtZD, invDupMatdict, perm=permdict[str(k)])

      # We need to modify by multiplying by this matrix
      chol_mod = elimMatdict[k] @ (scipy.sparse.identity(nparams[k]**2) + comMatdict[k]) @ scipy.sparse.kron(cholDict[k],np.eye(nparams[k])) @ elimMatdict[k].transpose()
      
      # Transform to cholesky
      dldcholk = chol_mod.transpose() @ mat2vech2D(dldD)
      covdldcholk = chol_mod.transpose() @ covdldDk @ chol_mod

      update = lam*forceSym2D(np.linalg.inv(covdldcholk)) @ dldcholk
    
      # Update D_k and chol
      cholDict[k] = vechTri2mat2D(mat2vechTri2D(cholDict[k]) + update)

      #print('cholDict',k)
      #print(cholDict[k])
      Ddict[k] = cholDict[k] @ cholDict[k].transpose()

      #print('D',k)
      #print(Ddict[k])

      # Add D_k back into D and recompute DinvIplusZtZD
      for j in np.arange(nlevels[k]):

        D[Dinds[counter]:Dinds[counter+1], Dinds[counter]:Dinds[counter+1]] = Ddict[k]
        counter = counter + 1
      
      # Inverse of (I+Z'ZD) multiplied by D
      IplusZtZD = np.eye(q) + (ZtZ @ D)
      t1 = time.time()
      DinvIplusZtZD = forceSym2D(D @ scipy.sparse.linalg.inv(scipy.sparse.csc_matrix(IplusZtZD)))
      t2 = time.time()
      #print('Inversion time:', t2-t1)
      #t1 = time.time()
      #DinvIplusZtZD = forceSym2D(D @ recursiveInverse2D(scipy.sparse.csc_matrix(IplusZtZD),nparams,nlevels))
      #t2 = time.time()
      #print('Inversion time2:', t2-t1)

    # Update the step size
    llhcurr = llh2D(n, ZtZ, Zte, ete, sigma2, DinvIplusZtZD,D)[0,0]
    if llhprev>llhcurr:
      lam = lam/2

  paramVector = np.concatenate((beta, sigma2))
  for k in np.arange(len(nparams)):
    paramVector = np.concatenate((paramVector, mat2vech2D(Ddict[k])))

  bvals = DinvIplusZtZD @ Zte
  
  print('nit',nit)

  return(paramVector, bvals)

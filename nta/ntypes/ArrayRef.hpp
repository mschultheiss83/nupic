/**
 * ----------------------------------------------------------------------
 *  Copyright (C) 2010 Numenta Inc. All rights reserved.
 *
 *  The information and source code contained herein is the
 *  exclusive property of Numenta Inc. No part of this software
 *  may be used, reproduced, stored or distributed in any form,
 *  without explicit written authorization from Numenta Inc.
 * ----------------------------------------------------------------------
 */

// ---
//
// Definitions for the ArrayRef class
//  
// It is a sub-class of ArrayBase that doesn't own its buffer
//
// ---

#ifndef NTA_ARRAY_REF_HPP
#define NTA_ARRAY_REF_HPP

#include <nta/ntypes/ArrayBase.hpp>
#include <nta/utils/Log.hpp>

namespace nta
{
  class ArrayRef : public ArrayBase
  {
  public:
    ArrayRef(NTA_BasicType type, void * buffer, size_t count) : ArrayBase(type)
    {
      setBuffer(buffer, count);
    }
    
    explicit ArrayRef(NTA_BasicType type) : ArrayBase(type)
    {
    }

    ArrayRef(const ArrayRef & other) : ArrayBase(other)
    {
    }
  
    void invariant()
    {
      if (own_)
        NTA_THROW << "ArrayRef mmust not own its buffer";
    }
  private:
    // Hide base class method (invalid for ArrayRef)
    void allocateBuffer(void * buffer, size_t count);
  };
}

#endif
